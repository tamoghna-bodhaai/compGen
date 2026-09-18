from __future__ import annotations


SYSTEM_PROMPT = """You are an independent JEE examination validator. Solve the question yourself. Do not trust the proposed answer or solution. Return only JSON that matches the requested schema."""


def build_prompt(*, question: dict, expected_type: str, expected_difficulty: int, expected_concepts: list[str]) -> str:
    return f"""Independently solve and assess this generated question.

Required output type: {expected_type}
Required difficulty (1-5): {expected_difficulty}
Expected concepts: {expected_concepts}

Check for ambiguity, multiple correct answers where not requested, missing data, answer inconsistency, concept mismatch, and difficulty mismatch. Do not repeat or rely on the supplied solution.

Question:
{question}
"""
