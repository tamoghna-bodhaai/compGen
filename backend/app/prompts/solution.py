from __future__ import annotations


SYSTEM_PROMPT = """You are a meticulous JEE Mathematics solution writer. Independently solve the supplied question, then provide a concise, rigorous step-by-step solution. Return only JSON matching the supplied schema. All mathematical notation must be valid LaTeX enclosed in the required delimiters."""


def build_prompt(*, question: dict, exam: str, subject: str) -> str:
    return f"""Write the answer and worked solution for this {exam} {subject} question.

Do not assume any existing answer key is correct. Derive the answer independently. Every mathematical expression—including substitutions, equations, intervals, trigonometric terms, and the final value—must be enclosed in literal $...$ (inline) or $$...$$ (display) delimiters. Never emit bare LaTeX commands or unwrapped mathematical notation. Use valid LaTeX commands with single backslashes, escaped correctly for JSON. For a single-correct MCQ, return the correct option letter when it can be determined; otherwise return null. Keep the solution appropriate for a student answer key.

Question:
{question}
"""
