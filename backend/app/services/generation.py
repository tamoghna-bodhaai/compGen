from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import UTC, datetime
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import ValidationError

from app.core.settings import Settings, get_settings
from app.db.database import get_connection
from app.prompts import concept_blueprint, concept_variation, solution, structural_variation, validator
from app.schemas.generation import (
    ConceptBlueprint,
    GeneratedQuestion,
    GeneratedSolution,
    GeneratedSlotResult,
    GenerationMode,
    GenerationRequest,
    GenerationResponse,
    GenerationSlot,
    ValidationResult,
)
from app.services.openrouter import ModelConfigurationError, OpenRouterClient, OpenRouterError
from app.services.retrieval import MetadataFirstRetriever, RetrievalCandidate


class GenerationFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class _Candidate:
    slot: GenerationSlot
    question: GeneratedQuestion
    seeds: list[RetrievalCandidate]
    similarity: float
    attempt: int


def _deterministic_failure(question: GeneratedQuestion, slot: GenerationSlot) -> str | None:
    """Reject malformed drafts locally; successful checks still need an LLM."""
    if question.question_type != slot.question_type:
        return "Generated question did not match the requested question type."
    if question.difficulty != slot.difficulty:
        return "Generated question did not match the requested difficulty."
    if not question.stem.strip() or not question.solution.strip() or not question.correct_answer.strip():
        return "Generated question is missing its stem, answer, or solution."
    if slot.question_type.value in {"single_correct_mcq", "multiple_correct_mcq"}:
        answer = question.correct_answer.strip()
        labels = {chr(ord("A") + index) for index in range(len(question.options))}
        if answer.upper() not in labels and answer not in question.options:
            return "MCQ answer does not identify one of the supplied options."
    return None


def _schema(model: type) -> dict:
    return model.model_json_schema()


def _text_terms(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", value.lower()))


def max_seed_similarity(question: GeneratedQuestion, seeds: list[RetrievalCandidate]) -> float:
    question_terms = _text_terms(question.stem)
    if not question_terms:
        return 0.0
    similarities = []
    for seed in seeds:
        seed_terms = _text_terms(seed.question_json["stem"])
        similarities.append(len(question_terms & seed_terms) / len(question_terms | seed_terms))
    return round(max(similarities, default=0.0), 4)


class GenerationService:
    def __init__(self, *, settings: Settings | None = None, client: OpenRouterClient | None = None, retriever: MetadataFirstRetriever | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client or OpenRouterClient(self.settings)
        self.retriever = retriever or MetadataFirstRetriever()

    async def generate(
        self,
        request: GenerationRequest,
        on_slot_complete: Callable[[GeneratedSlotResult], Awaitable[None] | None] | None = None,
        slots: list[GenerationSlot] | None = None,
        before_slot: Callable[[GenerationSlot], Awaitable[None] | None] | None = None,
        custom_instruction: str | None = None,
    ) -> GenerationResponse:
        if not self.settings.generation_ready:
            raise ModelConfigurationError(
                "Generation is not configured. Set OPENROUTER_API_KEY, GENERATION_MODEL, and VALIDATION_MODEL before generating questions."
            )
        pending = list(slots if slots is not None else request.build_slots())
        results: list[GeneratedSlotResult] = []

        # A round is deliberately staged: burst generation first, inexpensive
        # deterministic checks second, and independent LLM validation last.
        # Only failed slots re-enter a later round, so one bad draft never
        # cancels the rest of the paper.
        for attempt in range(1, self.settings.max_generation_attempts + 1):
            if not pending:
                break
            candidates, failures = await self._generate_candidates(request, pending, attempt, before_slot, custom_instruction)
            candidates, local_failures = await self._deterministically_validate(request, candidates)
            failures.update(local_failures)
            validated, validation_failures = await self._llm_validate(request, candidates)
            failures.update(validation_failures)

            for result in validated:
                results.append(result)
                if on_slot_complete:
                    notification = on_slot_complete(result)
                    if notification is not None:
                        await notification
            pending = [slot for slot in pending if slot.slot in failures]
            if pending and attempt == self.settings.max_generation_attempts:
                failed_slot = pending[0]
                raise GenerationFailure(
                    f"Generation failed for question slot {failed_slot.slot} after {attempt} attempts: {failures[failed_slot.slot]}"
                )
        results.sort(key=lambda result: result.slot.slot)
        return GenerationResponse(title=request.title, generation_mode=request.generation_mode, slots=results)

    async def generate_slot(self, request: GenerationRequest, slot: GenerationSlot, custom_instruction: str | None = None) -> GeneratedSlotResult:
        response = await self.generate(request, slots=[slot], custom_instruction=custom_instruction)
        return response.slots[0]

    async def _generate_candidates(
        self,
        request: GenerationRequest,
        slots: list[GenerationSlot],
        attempt: int,
        before_slot: Callable[[GenerationSlot], Awaitable[None] | None] | None,
        custom_instruction: str | None,
    ) -> tuple[list[_Candidate], dict[int, str]]:
        semaphore = asyncio.Semaphore(self.settings.generation_burst_concurrency)

        async def produce(slot: GenerationSlot) -> _Candidate:
            try:
                if before_slot:
                    notification = before_slot(slot)
                    if notification is not None:
                        await notification
                async with semaphore:
                    if before_slot:
                        notification = before_slot(slot)
                        if notification is not None:
                            await notification
                    seeds = self.retriever.retrieve(request, slot)
                    question = await self._generate_question(request, slot, seeds, custom_instruction)
                    similarity = max_seed_similarity(question, seeds)
                    if request.generation_mode == GenerationMode.CONCEPT and similarity > self.settings.max_seed_similarity:
                        raise GenerationFailure(f"Generated question is too similar to its seed pool ({similarity:.2f}).")
                    return _Candidate(slot, question, seeds, similarity, attempt)
            except (OpenRouterError, ValidationError, GenerationFailure) as error:
                self._log(request, slot=slot, status="retrying", failure_reason=str(error))
                raise

        return await self._collect(slots, produce)

    async def _deterministically_validate(
        self, request: GenerationRequest, candidates: list[_Candidate]
    ) -> tuple[list[_Candidate], dict[int, str]]:
        semaphore = asyncio.Semaphore(self.settings.deterministic_validation_concurrency)

        async def check(candidate: _Candidate) -> _Candidate:
            async with semaphore:
                failure = _deterministic_failure(candidate.question, candidate.slot)
                if failure:
                    self._log(request, slot=candidate.slot, seeds=candidate.seeds, status="retrying", failure_reason=failure)
                    raise GenerationFailure(failure)
                return candidate

        return await self._collect(candidates, check, key=lambda candidate: candidate.slot)

    async def _llm_validate(
        self, request: GenerationRequest, candidates: list[_Candidate]
    ) -> tuple[list[GeneratedSlotResult], dict[int, str]]:
        semaphore = asyncio.Semaphore(self.settings.validation_burst_concurrency)

        async def validate(candidate: _Candidate) -> GeneratedSlotResult:
            try:
                async with semaphore:
                    validation = await self._validate(candidate.question, request, candidate.slot)
                if not validation.valid or not self._validation_matches_requirements(validation):
                    raise GenerationFailure(validation.comments or "Independent validation failed.")
                result = GeneratedSlotResult(
                    slot=candidate.slot,
                    question=candidate.question,
                    seed_question_ids=[seed.id for seed in candidate.seeds],
                    similarity_score=candidate.similarity,
                    validation=validation,
                    generation_attempt=candidate.attempt,
                )
                self._log(request, result=result, status="validated")
                return result
            except (OpenRouterError, ValidationError, GenerationFailure) as error:
                self._log(request, slot=candidate.slot, seeds=candidate.seeds, status="retrying", failure_reason=str(error))
                raise

        return await self._collect(candidates, validate, key=lambda candidate: candidate.slot)

    @staticmethod
    async def _collect(items: list, worker: Callable, *, key: Callable | None = None) -> tuple[list, dict[int, str]]:
        key = key or (lambda item: item)
        outcomes = await asyncio.gather(*(worker(item) for item in items), return_exceptions=True)
        successes, failures = [], {}
        for item, outcome in zip(items, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                if isinstance(outcome, asyncio.CancelledError):
                    raise outcome
                slot = key(item)
                failures[slot.slot] = str(outcome)
            else:
                successes.append(outcome)
        return successes, failures

    async def generate_solution(self, question: dict, *, exam: str, subject: str) -> GeneratedSolution:
        if not self.settings.generation_ready:
            raise ModelConfigurationError(
                "Generation is not configured. Set OPENROUTER_API_KEY, GENERATION_MODEL, and VALIDATION_MODEL before generating solutions."
            )
        raw = await self.client.call_llm(
            model=self.settings.validation_model,
            system_prompt=solution.SYSTEM_PROMPT,
            user_prompt=solution.build_prompt(question=question, exam=exam, subject=subject),
            response_schema=_schema(GeneratedSolution),
            temperature=0.1,
            max_tokens=1800,
        )
        return GeneratedSolution.model_validate(raw)

    async def _generate_question(self, request: GenerationRequest, slot: GenerationSlot, seeds: list[RetrievalCandidate], custom_instruction: str | None = None) -> GeneratedQuestion:
        seed_payload = [seed.prompt_payload() for seed in seeds]
        mode = slot.generation_mode or request.generation_mode
        strength = slot.variation_strength or request.variation_strength
        if mode == GenerationMode.STRUCTURAL:
            raw = await self.client.call_llm(
                model=self.settings.generation_model,
                system_prompt=structural_variation.SYSTEM_PROMPT,
                user_prompt=structural_variation.build_prompt(
                    seeds=seed_payload, target_type=slot.question_type.value, difficulty=slot.difficulty,
                    variation_strength=strength.value, custom_instruction=custom_instruction,
                ),
                response_schema=_schema(GeneratedQuestion),
            )
        else:
            blueprint_raw = await self.client.call_llm(
                model=self.settings.generation_model,
                system_prompt=concept_blueprint.SYSTEM_PROMPT,
                user_prompt=concept_blueprint.build_prompt(
                    seeds=seed_payload, requested_concepts=request.concepts, target_type=slot.question_type.value,
                    difficulty=slot.difficulty, variation_strength=strength.value, custom_instruction=custom_instruction,
                ),
                response_schema=_schema(ConceptBlueprint),
                temperature=0.3,
                max_tokens=1200,
            )
            blueprint = ConceptBlueprint.model_validate(blueprint_raw)
            if blueprint.question_type != slot.question_type or blueprint.difficulty != slot.difficulty:
                raise GenerationFailure("Concept blueprint did not match the requested question type or difficulty.")
            raw = await self.client.call_llm(
                model=self.settings.generation_model,
                system_prompt=concept_variation.SYSTEM_PROMPT,
                user_prompt=concept_variation.build_prompt(seeds=seed_payload, blueprint=blueprint.model_dump(), custom_instruction=custom_instruction),
                response_schema=_schema(GeneratedQuestion),
            )
        question = GeneratedQuestion.model_validate(raw)
        if question.question_type != slot.question_type or question.difficulty != slot.difficulty:
            raise GenerationFailure("Generated question did not match the requested type or difficulty.")
        return question

    async def _validate(self, question: GeneratedQuestion, request: GenerationRequest, slot: GenerationSlot) -> ValidationResult:
        raw = await self.client.call_llm(
            model=self.settings.validation_model,
            system_prompt=validator.SYSTEM_PROMPT,
            user_prompt=validator.build_prompt(
                question=question.model_dump(), expected_type=slot.question_type.value,
                expected_difficulty=slot.difficulty, expected_concepts=request.concepts,
            ),
            response_schema=_schema(ValidationResult),
            temperature=0.0,
        )
        return ValidationResult.model_validate(raw)

    @staticmethod
    def _validation_matches_requirements(validation: ValidationResult) -> bool:
        return all((
            validation.matches_generated_answer,
            not validation.ambiguous,
            not validation.multiple_answers_possible,
            validation.sufficient_information,
            validation.concept_match,
            validation.difficulty_match,
        ))

    def _log(
        self,
        request: GenerationRequest,
        *,
        status: str,
        result: GeneratedSlotResult | None = None,
        slot: GenerationSlot | None = None,
        seeds: list[RetrievalCandidate] | None = None,
        failure_reason: str | None = None,
    ) -> None:
        if result:
            slot, seeds = result.slot, []
            validation_json = result.validation.model_dump_json()
            seed_ids = result.seed_question_ids
            similarity = result.similarity_score
        else:
            validation_json = None
            seed_ids = [seed.id for seed in seeds or []]
            similarity = None
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO generation_logs (id, request_json, generation_mode, model, status, failure_reason, seed_question_ids, validation_result_json, similarity_score, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()), request.model_dump_json(), request.generation_mode.value,
                    self.settings.generation_model, status, failure_reason, json.dumps(seed_ids), validation_json,
                    similarity, datetime.now(UTC).isoformat(),
                ),
            )
