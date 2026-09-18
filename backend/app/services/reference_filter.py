from __future__ import annotations

import re


def _parse_segment(segment: str, out: set[int]) -> None:
    s = segment.strip().lower()
    if not s:
        return
    # Strip leading q/qs/question/questions (longer alternative first to avoid partial 'q' match)
    s = re.sub(r"^(?:questions?|q(?:s)?)\s*\.?\s*", "", s)
    s = s.strip()
    if not s:
        return
    # Range: 10-20, 10 - 20, 10 to 20, 10..20, 10–20 (en dash)
    m_range = re.match(r"^(\d+)\s*(?:-|–|to|\.\.)\s*(\d+)$", s)
    if m_range:
        a, b = int(m_range.group(1)), int(m_range.group(2))
        if a > b:
            a, b = b, a
        for n in range(a, b + 1):
            if 1 <= n <= 500:
                out.add(n)
        return
    # Single number
    if re.match(r"^\d+$", s):
        n = int(s)
        if 1 <= n <= 500:
            out.add(n)
        return


def parse_reference_filter(text: str | None) -> set[int] | None:
    """
    Parse question number filters from free-form text or explicit input.

    Recognizes patterns like:
    - "10-20", "10 - 20", "10 to 20", "10..20"
    - "Q10-Q20", "Qs 10-20", "Question 10-20"
    - "10,12,15-18", "1, 5, 10-12 and 20"
    - "only 10-20", "refer to only questions 10-20 from pdf"

    Returns None if no filter is detectable (meaning: use full paper).
    Returns set of ints otherwise.
    """
    if not text:
        return None
    t = text.strip()
    if not t:
        return None

    # Fast path: if text looks like a simple explicit filter "10-20" or "1,2,3"
    # we can still use general parsing below, no special handling needed.

    # Normalize separators: replace 'and' with comma
    # Keep hyphens/ranges intact, just normalize surrounding words
    # Use lower for detection
    low = t.lower()

    # Heuristic: only attempt parsing if text contains numbers and
    # either a range indicator or explicit keyword
    # We allow both "10-20" alone and "only 10-20 from pdf"
    # If no digit, no filter.
    if not re.search(r"\d", t):
        return None

    # If text is short and is purely numbers/commas/ranges, parse directly
    # Otherwise scan for filter-like fragments.
    # Extract candidate fragments that look like number lists.
    # Approach: find all substrings that look like "q? <numbers/ranges separated by commas and/or 'and'>"
    # But simpler: split on commas/semicolons, handle each segment.

    # Normalize: replace semicolons with commas
    normalized = re.sub(r"[;]", ",", t)
    # Replace " and " with comma (case-insensitive)
    normalized = re.sub(r"\band\b", ",", normalized, flags=re.I)

    # Remove parenthetical noise: "(10-20)" -> "10-20"
    # We just keep content.

    # Split on commas
    parts = [p.strip() for p in normalized.split(",")]
    # If no commas, treat whole text as single potential segment, but need to
    # extract the number-range part from surrounding words.
    # Example: "refer to only questions 10-20 from the pdf" -> extract "10-20"
    # So we also scan for range/number patterns inside each part.

    result: set[int] = set()

    # For comma-split parts, further extract number-range tokens
    for part in parts:
        # If part already looks like a segment "10-20" or "Q5" -> parse
        # Otherwise, search within part for range/number patterns
        # Extract all occurrences of: optional q prefix + number + optional range
        # e.g. "refer to only questions 10-20 from pdf" -> find "10-20"
        # "Q10-Q20" -> find "Q10-Q20" as one? Actually Q10-Q20 contains two Q prefixes.
        # We'll find patterns: (?:q[s]?\s*\.?\s*)?\d+\s*(?:-|–|to|\.\.)\s*(?:q[s]?\s*\.?\s*)?\d+  OR single q?\d+

        # First, try to see if whole part is parsable as segment directly
        direct = part.strip()
        # Strip leading words like "only", "questions", "refer to", etc. by extracting the first range/single
        # So we search inside part.

        # Find ranges first
        range_pat = re.compile(r"(?:questions?|q(?:s)?)?\s*\.?\s*(\d+)\s*(?:-|–|to|\.\.)\s*(?:questions?|q(?:s)?)?\s*\.?\s*(\d+)", re.I)
        single_pat = re.compile(r"(?:questions?|q(?:s)?)?\s*\.?\s*(\d+)", re.I)

        found_range = False
        for m in range_pat.finditer(part):
            a, b = int(m.group(1)), int(m.group(2))
            if a > b:
                a, b = b, a
            for n in range(a, b + 1):
                if 1 <= n <= 500:
                    result.add(n)
            found_range = True

        if found_range:
            # Remove range matches to avoid double-counting singles inside them
            # by blanking them out, then check remaining singles
            cleaned = range_pat.sub(" ", part)
            for m in single_pat.finditer(cleaned):
                n = int(m.group(1))
                # Avoid adding numbers that are part of other words? Filter by context:
                # Heuristic: single numbers in free text like "35 MB" should not be treated as filter
                # So we only accept singles if part seems filter-like.
                # Criteria: part contains keywords "question", "q", "only", "refer", or is short (<30 chars) and mostly numbers/punctuation
                # We'll apply that check at the part level.
                is_filter_like = bool(re.search(r"\b(?:questions?|q(?:s)?|only|refer|filter)\b", part, re.I)) or (
                    len(part) < 30 and re.match(r"^[\d\s,\-–to.]+$", part.strip().lower())
                )
                if is_filter_like and 1 <= n <= 500:
                    result.add(n)
            continue

        # No range found, look for singles that are filter-like
        # e.g. "10, 12, 15" after comma split -> each part is "10" -> accept
        # But "35 MB" -> should be ignored
        if re.match(r"^\s*(?:questions?|q(?:s)?)?\s*\.?\s*\d+\s*$", part, re.I):
            _parse_segment(part, result)
        else:
            # Try to find single numbers that are clearly question references
            # Only if part contains question keywords or is very short numeric
            # Example: "use only 10-20" already handled as range above.
            # For edge like "question 5", find "5"
            # We'll extract singles with keyword proximity
            for m in single_pat.finditer(part):
                # Check surrounding context includes question/q/only
                snippet = part[max(0, m.start() - 20): m.end() + 20]
                is_filter_like = bool(re.search(r"\b(?:questions?|q(?:s)?|only|refer|filter)\b", snippet, re.I)) or (
                    len(part) < 30 and re.match(r"^[\d\s,\-–to.]+$", part.strip().lower())
                )
                if is_filter_like:
                    n = int(m.group(1))
                    if 1 <= n <= 500:
                        result.add(n)

    if not result:
        return None
    return result


def format_filter(numbers: set[int]) -> str:
    """Human-readable like 10-20,25,30-32"""
    if not numbers:
        return ""
    sorted_nums = sorted(numbers)
    ranges: list[str] = []
    start = prev = sorted_nums[0]
    for n in sorted_nums[1:]:
        if n == prev + 1:
            prev = n
        else:
            if start == prev:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}-{prev}")
            start = prev = n
    if start == prev:
        ranges.append(str(start))
    else:
        ranges.append(f"{start}-{prev}")
    return ",".join(ranges)
