from __future__ import annotations


SYSTEM_PROMPT = """You create rigorous JEE-level examination questions. Return only JSON that matches the requested schema. Mathematical content uses LaTeX inside strings."""


def build_prompt(*, seeds: list[dict], target_type: str, difficulty: int, variation_strength: str, custom_instruction: str | None = None) -> str:
    return f"""Create one structurally varied question.

Target output type: {target_type}
Target difficulty (1-5): {difficulty}
Variation strength: {variation_strength}
Custom regeneration instruction: {custom_instruction or "None"}

Use the supplied seed questions only as grounding. Preserve the core concept, question archetype, approximate solution strategy, and reasoning depth. Change values, parameters, wording, notation, and setup enough that the result is not a paraphrase. The question must be complete, solvable, and have an answer consistent with its solution.

Seed questions:
{seeds}
"""
