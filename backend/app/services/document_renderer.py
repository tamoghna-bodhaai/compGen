from __future__ import annotations

import base64
import io
import re
import shutil
import subprocess
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt, RGBColor
from lxml import etree

from app.schemas.papers import ExportFormat, ExportVariant


class DocumentRenderError(RuntimeError):
    pass


_SUPERSCRIPT = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")
_SUBSCRIPT = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
_COMMANDS = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "Delta": "Δ", "theta": "θ",
    "lambda": "λ", "mu": "μ", "pi": "π", "rho": "ρ", "sigma": "σ", "Sigma": "Σ",
    "phi": "φ", "omega": "ω", "infty": "∞", "int": "∫", "sum": "Σ", "prod": "∏",
    "leq": "≤", "geq": "≥", "neq": "≠", "ne": "≠", "times": "×", "cdot": "·", "pm": "±",
    "to": "→", "rightarrow": "→", "in": "∈", "notin": "∉", "cup": "∪", "cap": "∩",
    "log": "log", "sin": "sin", "cos": "cos", "tan": "tan", "ln": "ln", "ell": "ℓ",
    "partial": "∂", "degree": "°", "cdots": "…", "lim": "lim",
}

# The paper source stores mathematical notation as LaTeX.  Exporting that text
# after a Unicode-only substitution makes fractions, limits and integrals lose
# their mathematical structure.  The small parser below covers the JEE syntax
# used by the seed bank and generated questions, and emits Office Math Markup
# Language (OMML): the native equation format used by DOCX/Word.
_MATH_SYMBOLS = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "Delta": "Δ", "theta": "θ",
    "lambda": "λ", "mu": "μ", "pi": "π", "rho": "ρ", "sigma": "σ", "Sigma": "Σ",
    "phi": "φ", "omega": "ω", "infty": "∞", "ell": "ℓ", "leq": "≤", "geq": "≥",
    "le": "≤", "ge": "≥", "neq": "≠", "ne": "≠", "times": "×", "cdot": "·", "pm": "±", "mp": "∓",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "in": "∈", "notin": "∉",
    "cup": "∪", "cap": "∩", "partial": "∂", "degree": "°", "cdots": "⋯",
    "vdots": "⋮", "ddots": "⋱",
    "ldots": "…", "dots": "…", "approx": "≈", "equiv": "≡", "parallel": "∥",
    "perp": "⊥", "forall": "∀", "exists": "∃", "therefore": "∴",
    "vert": "|", "Vert": "‖", "mid": "|", "langle": "⟨", "rangle": "⟩",
    "lceil": "⌈", "rceil": "⌉", "lfloor": "⌊", "rfloor": "⌋",
}
_MATH_FUNCTIONS = {"sin", "cos", "tan", "cot", "sec", "csc", "log", "ln", "exp", "det", "max", "min", "lim"}
# Keep these as ordinary Office-math bases.  An ``m:nary`` requires its entire
# integrand in its ``m:e`` child, which is not compatible with a mixed prose /
# math paragraph.  Scripted symbols render correctly inline and keep the
# following fraction or integrand on the same baseline.
_NARY_SYMBOLS = {"int": "∫", "iint": "∬", "iiint": "∭", "oint": "∮", "sum": "∑", "prod": "∏"}
_MATH_SPACING = {",", "!", ";", ":", "quad", "qquad", "enspace", "thinspace", " "}


def _xml_safe_text(value: Any) -> str:
    """Remove characters WordprocessingML cannot represent.

    Model output can occasionally contain a decoded JSON control character
    (for example, a tab or backspace in place of a LaTeX command).  lxml and
    python-docx reject those characters during DOCX generation.  Keep normal
    whitespace, but remove every other XML 1.0-invalid code point at the
    rendering boundary so a single malformed question cannot block an export.
    """
    text = str(value or "")
    return "".join(
        character
        for character in text
        if character in "\t\n\r"
        or 0x20 <= ord(character) <= 0xD7FF
        or 0xE000 <= ord(character) <= 0xFFFD
        or 0x10000 <= ord(character) <= 0x10FFFF
    )


def _braced_group(value: str, start: int) -> tuple[str, int] | None:
    if start >= len(value) or value[start] != "{":
        return None
    depth = 0
    for index in range(start, len(value)):
        if value[index] == "{":
            depth += 1
        elif value[index] == "}":
            depth -= 1
            if depth == 0:
                return value[start + 1:index], index + 1
    return None


def _replace_grouped_command(value: str, command: str, formatter: Any) -> str:
    cursor = 0
    while (start := value.find(command, cursor)) >= 0:
        first = _braced_group(value, start + len(command))
        if first is None:
            cursor = start + len(command)
            continue
        second = _braced_group(value, first[1])
        if second is None:
            cursor = start + len(command)
            continue
        value = value[:start] + formatter(first[0], second[0]) + value[second[1]:]
        cursor = start
    return value


def _normalize_latex(value: str) -> str:
    """Collapse transport-escaped backslashes and repair JSON control chars."""
    value = _xml_safe_text(value).replace(chr(92) * 2, chr(92))
    # Model/JSON round-trips occasionally decode \f \t \b \r \a as controls.
    value = (
        value.replace("\x0crac", "\\frac")
        .replace("\x09an", "\\tan").replace("\x09ext", "\\text")
        .replace("\x08egin", "\\begin").replace("\x08ox", "\\box")
        .replace("\rod", "\\rod").replace("\right", "\\right")
        .replace("\x07sqrt", "\\sqrt")
    )
    return value


def latex_to_readable(value: str) -> str:
    """Convert common source-bank LaTex to durable printable Unicode notation."""
    # Seed JSON preserves backslashes for transport, so imported LaTex can have
    # two physical backslashes before every command. Normalise it first.
    value = _normalize_latex(value)
    value = value.replace("$", "")
    # Strip math delimiters used by generation pipelines: \(...\), \[...\].
    value = value.replace("\\(", "").replace("\\)", "").replace("\\[", "").replace("\\]", "")
    value = value.replace("\\,", " ").replace("\\!", "").replace("\\;", " ").replace("\\:", " ").replace("\\quad", " ").replace("\\qquad", "  ")
    value = value.replace("\\left", "").replace("\\right", "")
    value = _replace_grouped_command(value, "\\frac", lambda numerator, denominator: f"({numerator})/({denominator})")
    root = re.compile(r"\\sqrt\s*\{([^{}]*)\}")
    previous = None
    while value != previous:
        previous = value
        value = root.sub(lambda match: f"√({match.group(1)})", value)
    value = re.sub(r"\\frac([A-Za-z0-9])\{([^{}]*)\}", r"(\1)/(\2)", value)
    value = re.sub(r"\\frac\{([^{}]*)\}([A-Za-z0-9])", r"(\1)/(\2)", value)
    value = re.sub(r"\\frac([A-Za-z0-9])([A-Za-z0-9])", r"(\1)/(\2)", value)
    value = re.sub(r"\\sqrt([A-Za-z0-9])", r"√(\1)", value)

    def script(match: re.Match[str]) -> str:
        marker, group, token = match.group(1), match.group(2), match.group(3)
        content = group if group is not None else token
        table = _SUPERSCRIPT if marker == "^" else _SUBSCRIPT
        if re.fullmatch(r"[0-9+\-=()]+", content):
            return content.translate(table)
        readable_scripts = {"^n": "ⁿ", "^r": "ʳ", "^k": "ᵏ", "^x": "ˣ", "^a": "ᵃ", "^b": "ᵇ", "_n": "ₙ", "_r": "ᵣ", "_x": "ₓ", "_a": "ₐ", "_b": "ᵦ"}
        if len(content) == 1 and f"{marker}{content}" in readable_scripts:
            return readable_scripts[f"{marker}{content}"]
        if marker == "_" and re.fullmatch(r"[a-zA-Z0-9+=-]+", content):
            return "".join(readable_scripts.get(f"_{character}", character.translate(_SUBSCRIPT)) for character in content)
        return f" ({content})" if marker == "_" else f"^({content})"

    value = re.sub(r"\\([A-Za-z]+)", lambda match: _COMMANDS.get(match.group(1), match.group(1)), value)
    value = re.sub(r"([_^])(?:\{([^{}]*)\}|([A-Za-z0-9]))", script, value)
    value = value.replace("{", "(").replace("}", ")")
    return _xml_safe_text(re.sub(r"\s+", " ", value).strip())


MathNode = tuple[Any, ...]


class _LatexMathParser:
    """Deliberately small LaTeX parser for native Office math export."""

    def __init__(self, value: str) -> None:
        self.value = value.replace(chr(92) * 2, chr(92))
        self.index = 0

    def parse(self) -> MathNode:
        return self._row(self._sequence())

    @staticmethod
    def _row(items: list[MathNode]) -> MathNode:
        return items[0] if len(items) == 1 else ("row", tuple(items))

    def _sequence(self, stop: str | None = None) -> list[MathNode]:
        items: list[MathNode] = []
        while self.index < len(self.value):
            if stop and self.value[self.index] == stop:
                self.index += 1
                break
            if self.value[self.index] == "}":
                break
            if self.value[self.index] in "^_":
                # A malformed leading script should not leak a TeX marker into
                # an exported document.
                self.index += 1
                self._atom()
                continue
            items.append(self._atom())
        return items

    def _atom(self) -> MathNode:
        if self.index >= len(self.value):
            return ("text", "")
        character = self.value[self.index]
        if character == "{":
            self.index += 1
            node = self._row(self._sequence("}"))
        elif character == "\\":
            node = self._command()
        elif character.isspace() or character == "~":
            self.index += 1
            node = ("text", " ")
        else:
            self.index += 1
            node = ("text", character)
        return self._scripts(node)

    def _required_atom(self) -> MathNode:
        if self.index >= len(self.value):
            return ("text", "")
        return self._atom()

    def _script_argument(self) -> MathNode:
        """Read exactly one script argument, without consuming the next script."""
        if self.index >= len(self.value):
            return ("text", "")
        if self.value[self.index] == "{":
            self.index += 1
            return self._row(self._sequence("}"))
        if self.value[self.index] == "\\":
            return self._command()
        character = self.value[self.index]
        self.index += 1
        return ("text", character)

    def _command(self) -> MathNode:
        self.index += 1
        if self.index >= len(self.value):
            return ("text", "")
        if not self.value[self.index].isalpha():
            escaped = self.value[self.index]
            self.index += 1
            # TeX spacing/line-break escapes are not printable content.
            if escaped in {",", ";", ":", "!", " ", "/", "|"}:
                return ("text", " " if escaped in {",", ";", ":", " "} else escaped)
            if escaped in {"(", ")", "[", "]", "{", "}", "."}:
                return ("text", escaped)
            return ("text", escaped)
        start = self.index
        while self.index < len(self.value) and self.value[self.index].isalpha():
            self.index += 1
        command = self.value[start:self.index]
        if command in _MATH_SPACING or command in {"left", "right", "limits", "nolimits", "displaystyle", "textstyle", "scriptstyle", "scriptscriptstyle"}:
            return ("text", "")
        if command in {"frac", "dfrac", "tfrac"}:
            return ("fraction", self._required_atom(), self._required_atom())
        if command == "sqrt":
            if self.index < len(self.value) and self.value[self.index] == "[":
                # Indexed radicals are uncommon in the supplied syllabus. Keep
                # their degree visible even when emitting a standard radical.
                end = self.value.find("]", self.index + 1)
                if end >= 0:
                    self.index = end + 1
            return ("radical", self._required_atom())
        if command in _NARY_SYMBOLS:
            return ("text", _NARY_SYMBOLS[command])
        if command in _MATH_FUNCTIONS:
            return ("text", command)
        if command in {"mathbb", "mathrm", "mathit", "mathbf", "text", "operatorname", "overline", "underline"}:
            return self._required_atom()
        if command in _MATH_SYMBOLS:
            return ("text", _MATH_SYMBOLS[command])
        # Preserve the useful name, never the raw command/backslash.
        return ("text", command)

    def _scripts(self, base: MathNode) -> MathNode:
        sub: MathNode | None = None
        sup: MathNode | None = None
        while self.index < len(self.value) and self.value[self.index] in "^_":
            marker = self.value[self.index]
            self.index += 1
            value = self._script_argument()
            if marker == "_":
                sub = value
            else:
                sup = value
        if sub is not None and sup is not None:
            return ("subsup", base, sub, sup)
        if sub is not None:
            return ("sub", base, sub)
        if sup is not None:
            return ("sup", base, sup)
        return base


def _math_element(name: str) -> Any:
    return OxmlElement(f"m:{name}")


def _math_text(value: str) -> Any:
    run = _math_element("r")
    text = _math_element("t")
    value = _xml_safe_text(value)
    text.text = value
    if value.startswith(" ") or value.endswith(" "):
        text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    run.append(text)
    return run


def _append_math(parent: Any, node: MathNode) -> None:
    kind = node[0]
    if kind == "text":
        if node[1]:
            parent.append(_math_text(node[1]))
        return
    if kind == "row":
        for item in node[1]:
            _append_math(parent, item)
        return
    if kind == "fraction":
        fraction = _math_element("f")
        numerator, denominator = _math_element("num"), _math_element("den")
        _append_math(numerator, node[1])
        _append_math(denominator, node[2])
        fraction.extend((numerator, denominator))
        parent.append(fraction)
        return
    if kind == "radical":
        radical = _math_element("rad")
        properties = _math_element("radPr")
        degree_hidden = _math_element("degHide")
        degree_hidden.set(qn("m:val"), "1")
        properties.append(degree_hidden)
        # OMML requires a degree child even when the degree is hidden.  Without
        # it LibreOffice shows an empty square after the radical sign.
        degree = _math_element("deg")
        expression = _math_element("e")
        _append_math(expression, node[1])
        radical.extend((properties, degree, expression))
        parent.append(radical)
        return
    if kind in {"sub", "sup", "subsup"}:
        element = _math_element({"sub": "sSub", "sup": "sSup", "subsup": "sSubSup"}[kind])
        base = _math_element("e")
        _append_math(base, node[1])
        element.append(base)
        if kind in {"sub", "subsup"}:
            subscript = _math_element("sub")
            _append_math(subscript, node[2])
            element.append(subscript)
        if kind == "sup":
            superscript = _math_element("sup")
            _append_math(superscript, node[2])
            element.append(superscript)
        elif kind == "subsup":
            superscript = _math_element("sup")
            _append_math(superscript, node[3])
            element.append(superscript)
        parent.append(element)


def _append_omml(paragraph: Any, latex: str) -> None:
    equation = _math_element("oMath")
    try:
        _append_math(equation, _LatexMathParser(latex).parse())
    except (IndexError, ValueError):
        # A malformed model response is still safe to export as readable text.
        equation.append(_math_text(latex_to_readable(latex)))
    paragraph._p.append(equation)


_MATH_SPLIT = re.compile(r"(\$\$.*?\$\$|\\\[.*?\\\]|\\\(.*?\\\)|\$[^$\n]+?\$)", flags=re.DOTALL)


def _split_math_segments(value: str) -> list[tuple[str, str]]:
    """Split mixed prose/LaTeX into (kind, content) with kind in text/inline/display."""
    value = _normalize_latex(value)
    segments: list[tuple[str, str]] = []
    cursor = 0
    for match in _MATH_SPLIT.finditer(value):
        if match.start() > cursor:
            segments.append(("text", value[cursor:match.start()]))
        token = match.group(1)
        if token.startswith("$$"):
            segments.append(("display", token[2:-2]))
        elif token.startswith("\\["):
            segments.append(("display", token[2:-2]))
        elif token.startswith("\\("):
            segments.append(("inline", token[2:-2]))
        else:
            segments.append(("inline", token[1:-1]))
        cursor = match.end()
    if cursor < len(value):
        segments.append(("text", value[cursor:]))
    return segments if segments else [("text", value)]


def _clean_prose(value: str) -> str:
    cleaned = _normalize_latex(value)
    cleaned = cleaned.replace("\\(", "").replace("\\)", "").replace("\\[", "").replace("\\]", "")
    cleaned = cleaned.replace("$", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return _xml_safe_text(cleaned)


def _append_latex_content(paragraph: Any, value: str, *, math_size: Pt | None = None) -> None:
    """Append prose plus native OMML equations, without visible TeX delimiters."""
    for kind, content in _split_math_segments(value):
        if not content:
            continue
        if kind == "text":
            # Unmatched dollar signs are formatting delimiters, not content.
            run = paragraph.add_run(latex_to_readable(content) if "\\" in content else content.replace("$", ""))
            if math_size is not None:
                run.font.size = math_size
        elif kind == "display":
            _append_omml(paragraph, content.strip())
        else:
            _append_omml(paragraph, content)


def _add_mixed_paragraphs(container: Any, value: str, *, style: Any = None, centered_display: bool = True) -> list[Any]:
    """Add prose with display equations on centred lines, like KaTeX output.

    Returns the created paragraphs so callers can style them further.
    """
    add = container.add_paragraph if hasattr(container, "add_paragraph") else None
    paragraphs: list[Any] = []
    current = container.add_paragraph(style=style) if add else None
    if current is None:  # table cell
        current = container.paragraphs[0] if container.paragraphs else container.add_paragraph(style=style)
        current.text = ""
    paragraphs.append(current)
    for kind, content in _split_math_segments(value):
        if not content:
            continue
        if kind == "display" and content.strip():
            display = container.add_paragraph()
            display.alignment = WD_ALIGN_PARAGRAPH.CENTER if centered_display else WD_ALIGN_PARAGRAPH.LEFT
            _append_omml(display, content.strip())
            paragraphs.append(display)
            current = container.add_paragraph(style=style) if add else container.add_paragraph()
            paragraphs.append(current)
        elif kind == "inline":
            _append_omml(current, content)
        else:
            text = _clean_prose(content)
            if text:
                current.add_run(text)
    return paragraphs


def _plain_length(value: str) -> int:
    return len(re.sub(r"\s+", "", latex_to_readable(value)))


def _shade(cell: Any, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    properties.append(shading)


def _set_cell_borders(cell: Any, *, visible: bool = True) -> None:
    properties = cell._tc.get_or_add_tcPr()
    borders = properties.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        properties.append(borders)
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node = borders.find(qn(f"w:{side}"))
        if node is None:
            node = OxmlElement(f"w:{side}")
            borders.append(node)
        node.set(qn("w:val"), "single" if visible else "nil")
        node.set(qn("w:sz"), "4" if visible else "0")
        node.set(qn("w:color"), "auto" if visible else "FFFFFF")


def _set_cell_padding(cell: Any, value: int = 100) -> None:
    properties = cell._tc.get_or_add_tcPr()
    margins = properties.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        properties.append(margins)
    for side in ("top", "start", "bottom", "end"):
        node = margins.find(qn(f"w:{side}"))
        if node is None:
            node = OxmlElement(f"w:{side}")
            margins.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def _page_field(paragraph: Any) -> None:
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    paragraph.add_run("Page ")._r.addnext(field)


def _logo_stream(branding: dict[str, Any]) -> io.BytesIO | None:
    value = branding.get("logo_data_url")
    if not isinstance(value, str) or not value.startswith("data:image/") or "," not in value:
        return None
    try:
        payload = base64.b64decode(value.split(",", 1)[1], validate=True)
    except (ValueError, base64.binascii.Error):
        return None
    if not payload or len(payload) > 750 * 1024:
        return None
    return io.BytesIO(payload)


def _add_watermark(paragraph: Any, text: str) -> None:
    """Add a Word-compatible, behind-text VML watermark to the header."""
    run = paragraph.add_run()
    picture = OxmlElement("w:pict")
    vml_namespace = "urn:schemas-microsoft-com:vml"
    shape = etree.Element(f"{{{vml_namespace}}}shape", nsmap={"v": vml_namespace})
    shape.set("id", "QuestionPaperWatermark")
    shape.set("type", "#_x0000_t136")
    shape.set("style", "position:absolute;width:468pt;height:117pt;rotation:315;z-index:-251654144;mso-position-horizontal:center;mso-position-horizontal-relative:margin;mso-position-vertical:center;mso-position-vertical-relative:margin")
    shape.set("fillcolor", "#d9d9d9")
    shape.set("stroked", "f")
    text_path = etree.Element(f"{{{vml_namespace}}}textpath")
    text_path.set("style", 'font-family:"Times New Roman";font-size:1pt')
    text_path.set("string", text[:80])
    shape.append(text_path)
    picture.append(shape)
    run._r.append(picture)


class PaperDocumentRenderer:
    def __init__(self, output_root: Path | None = None) -> None:
        self.output_root = output_root or Path(__file__).resolve().parents[3] / "output" / "exports"

    def export(self, paper: dict[str, Any], *, output_format: ExportFormat, variant: ExportVariant) -> tuple[Path, str]:
        if not paper["questions"]:
            raise DocumentRenderError("Add at least one question before exporting this paper.")
        self.output_root.mkdir(parents=True, exist_ok=True)
        stem = self._safe_filename(f"{paper['title']}_{variant.value}_{uuid.uuid4().hex[:8]}")
        if output_format == ExportFormat.DOCX:
            docx_path = self.output_root / f"{stem}.docx"
            self._build_docx(paper, variant, docx_path)
            return docx_path, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        # Publication-quality PDF via LaTeX (same source math as the KaTeX UI).
        # Fall back to DOCX->PDF conversion only when LaTeX is unavailable.
        try:
            return self._build_pdf_via_latex(paper, variant, stem), "application/pdf"
        except DocumentRenderError as exc:
            if "LaTeX" not in str(exc) and "pdflatex" not in str(exc).lower() and "latex" not in str(exc).lower():
                raise
            docx_path = self.output_root / f"{stem}.docx"
            self._build_docx(paper, variant, docx_path)
            return self._convert_to_pdf(docx_path), "application/pdf"

    @staticmethod
    def _safe_filename(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")[:120] or "question_paper"

    def _build_docx(self, paper: dict[str, Any], variant: ExportVariant, destination: Path) -> None:
        branding = paper.get("branding_config") or {}
        doc = Document()
        section = doc.sections[0]
        # Mirror the canonical LaTeX export: A4 with 19 mm side and 17 mm
        # top/bottom margins, independent of subject or source question type.
        section.page_width, section.page_height = Mm(210), Mm(297)
        section.top_margin, section.bottom_margin = Mm(17), Mm(17)
        section.left_margin, section.right_margin = Mm(19), Mm(19)
        section.header_distance, section.footer_distance = Inches(0.3), Inches(0.3)
        self._configure_styles(doc)
        self._add_header_footer(doc, branding)
        self._add_title_block(doc, paper, branding, variant)
        if variant == ExportVariant.ANSWER_KEY:
            self._add_answer_key(doc, paper)
        else:
            self._add_questions(doc, paper)
        doc.save(destination)

    @staticmethod
    def _configure_styles(doc: Document) -> None:
        normal = doc.styles["Normal"]
        normal.font.name, normal.font.size, normal.font.color.rgb = "Times New Roman", Pt(10.5), RGBColor(0, 0, 0)
        normal.paragraph_format.space_after, normal.paragraph_format.line_spacing = Pt(5), 1.08
        for name, size in (("Title", 18), ("Heading 1", 13), ("Heading 2", 11)):
            style = doc.styles[name]
            style.font.name, style.font.size, style.font.color.rgb = "Times New Roman", Pt(size), RGBColor(0, 0, 0)
            style.font.bold = True
            style.paragraph_format.space_before, style.paragraph_format.space_after = Pt(10 if name != "Title" else 0), Pt(6)
        title_borders = doc.styles["Title"]._element.pPr.find(qn("w:pBdr"))
        if title_borders is not None:
            doc.styles["Title"]._element.pPr.remove(title_borders)
        if "Question" not in doc.styles:
            question = doc.styles.add_style("Question", WD_STYLE_TYPE.PARAGRAPH)
            question.base_style, question.font.name, question.font.size = doc.styles["Normal"], "Times New Roman", Pt(10.5)
            question.font.bold = True
            question.paragraph_format.space_before, question.paragraph_format.space_after = Pt(8), Pt(3)

    @staticmethod
    def _add_header_footer(doc: Document, branding: dict[str, Any]) -> None:
        section = doc.sections[0]
        section.different_first_page_header_footer = False
        header = section.header.paragraphs[0]
        header.alignment = WD_ALIGN_PARAGRAPH.CENTER
        logo = _logo_stream(branding)
        if logo is not None:
            header.add_run().add_picture(logo, width=Inches(0.34))
            header.add_run("  ")
        header_text = str(branding.get("header_text") or branding.get("institution_name") or "Question Paper")
        header.add_run(header_text).bold = True
        contact_line = " · ".join(part for part in (str(branding.get("address") or "").strip(), str(branding.get("contact") or "").strip()) if part)
        if contact_line:
            line = section.header.add_paragraph(contact_line)
            line.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in line.runs:
                run.font.size = Pt(8)
        watermark = str(branding.get("watermark_text") or "").strip()
        if watermark:
            _add_watermark(header, watermark)
        footer = section.footer.paragraphs[0]
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer_text = str(branding.get("footer_text") or "").strip()
        if footer_text:
            footer.add_run(f"{footer_text}  ·  ")
        _page_field(footer)

    def _add_title_block(self, doc: Document, paper: dict[str, Any], branding: dict[str, Any], variant: ExportVariant) -> None:
        section = doc.sections[0]
        institution = branding.get("institution_name")
        if institution:
            paragraph = doc.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_after = Pt(1)
            run = paragraph.add_run(str(institution))
            run.bold, run.font.size = True, Pt(13)
        address = str(branding.get("address") or "").strip()
        if address:
            address_line = doc.add_paragraph()
            address_line.alignment = WD_ALIGN_PARAGRAPH.CENTER
            address_line.paragraph_format.space_after = Pt(1)
            run = address_line.add_run(address)
            run.italic, run.font.size = True, Pt(8.5)
        # Coaching-sheet header: Marks left, Time right, heavy rules above/below.
        marks = branding.get("total_marks")
        duration = branding.get("duration_minutes")
        marks_text = f"Marks : {marks}" if marks not in (None, "") else f"Marks : {sum(int((q.get('question_json') or {}).get('marks') or 0) for q in paper['questions'])}"
        duration_text = f"Time : {self._format_duration(duration)}" if duration not in (None, "") else "Time : 2 : 30 hours"
        meta = doc.add_paragraph()
        meta.paragraph_format.space_before, meta.paragraph_format.space_after = Pt(4), Pt(2)
        meta.add_run(marks_text).bold = True
        meta.add_run("\t")
        tail = meta.add_run(duration_text)
        tail.bold = True
        meta.paragraph_format.tab_stops.add_tab_stop(section.page_width - section.left_margin - section.right_margin, WD_ALIGN_PARAGRAPH.RIGHT)
        self._add_horizontal_rule(doc, bold=True)
        title = doc.add_paragraph(style="Title")
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title.paragraph_format.space_before, title.paragraph_format.space_after = Pt(4), Pt(1)
        title_run = title.add_run(str(paper["title"]).upper() + (" — ANSWER KEY" if variant == ExportVariant.ANSWER_KEY else ""))
        title_run.font.name = "Times New Roman"
        title_run.font.bold = True
        fonts = title_run._element.get_or_add_rPr().get_or_add_rFonts()
        for attribute in ("ascii", "hAnsi", "eastAsia", "cs"):
            fonts.set(qn(f"w:{attribute}"), "Times New Roman")
        subtitle = doc.add_paragraph()
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
        subtitle.paragraph_format.space_after = Pt(2)
        run = subtitle.add_run(f"{paper['exam']}  |  {paper['subject']}")
        run.font.size = Pt(9.5)
        self._add_horizontal_rule(doc, bold=True)
        details = doc.add_table(rows=1, cols=3)
        details.style = "Table Grid"
        detail_values = (
            ("Duration", self._format_duration(duration) if duration not in (None, "") else "Not specified"),
            ("Total Marks", str(marks) if marks not in (None, "") else str(sum(int((q.get('question_json') or {}).get('marks') or 0) for q in paper['questions']))),
            ("Questions", str(len(paper["questions"]))),
        )
        for index, (label, value) in enumerate(detail_values):
            cell = details.cell(0, index)
            cell.text = ""
            label_run = cell.paragraphs[0].add_run(f"{label}: ")
            label_run.bold = True
            label_run.font.size = Pt(9)
            value_run = cell.paragraphs[0].add_run(value)
            value_run.font.size = Pt(9)
            _set_cell_padding(cell)
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph()
        if variant == ExportVariant.QUESTION_PAPER:
            candidate = doc.add_table(rows=1, cols=2)
            candidate.style = "Table Grid"
            candidate.cell(0, 0).text, candidate.cell(0, 1).text = "Candidate Name: ______________________________", "Roll Number: __________________"
            for cell in candidate.rows[0].cells:
                _set_cell_padding(cell, 120)
            doc.add_paragraph("Instructions", style="Heading 2")
            for instruction in branding.get("instructions") or [
                "Read every question carefully before selecting an answer.",
                "For single-correct questions, mark one option only.",
                "Use the answer sheet or space provided by the invigilator.",
            ]:
                doc.add_paragraph(str(instruction), style="List Bullet")

    @staticmethod
    def _format_duration(value: Any) -> str:
        try:
            minutes = int(value)
        except (TypeError, ValueError):
            return str(value)
        if minutes >= 60:
            return f"{minutes // 60} : {minutes % 60:02d} hours"
        return f"{minutes} minutes"

    @staticmethod
    def _add_horizontal_rule(doc: Document, *, bold: bool = False) -> None:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_before, paragraph.paragraph_format.space_after = Pt(1), Pt(4)
        run = paragraph.add_run("─" * 88)
        run.font.size = Pt(7 if bold else 6)
        run.bold = bold

    def _add_questions(self, doc: Document, paper: dict[str, Any]) -> None:
        grouped: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        for question in paper["questions"]:
            grouped[question["section_id"]].append(question)
        titles = {section["id"]: section["title"] for section in paper["sections"]}
        number = 1
        ordered_section_ids = [section["id"] for section in paper["sections"]]
        for section_id in [*ordered_section_ids, None]:
            questions = grouped.get(section_id, [])
            if not questions:
                continue
            if section_id is not None:
                doc.add_paragraph(titles.get(section_id, "Section"), style="Heading 1")
            elif ordered_section_ids:
                doc.add_paragraph("Unsectioned questions", style="Heading 1")
            for question in sorted(questions, key=lambda item: item["position"]):
                payload = question["question_json"]
                stem = str(payload.get("stem", ""))
                options = list(payload.get("options") or [])
                # Keep the number with the first stem line; display equations
                # then flow centred exactly like the KaTeX preview.
                segments = _split_math_segments(stem)
                line = doc.add_paragraph(style="Question")
                line.add_run(f"{number}. ")
                has_content = False
                for kind, content in segments:
                    if not content or (kind == "text" and not _clean_prose(content)):
                        continue
                    if kind == "display" and content.strip():
                        display = doc.add_paragraph()
                        display.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        _append_omml(display, content.strip())
                        has_content = True
                        line = doc.add_paragraph(style="Normal")
                        continue
                    if kind == "inline":
                        _append_omml(line, content)
                    else:
                        line.add_run(_clean_prose(content))
                    has_content = True
                if payload.get("marks"):
                    doc.paragraphs[-1].add_run(f"  [{payload['marks']} marks]").italic = True
                self._add_options_table(doc, options)
                number += 1

    @staticmethod
    def _add_options_table(doc: Document, options: list[str]) -> None:
        if not options:
            return
        # Same grid width as the PDF export so both position options alike:
        # short options 4-across, medium options 2x2, long options stacked.
        columns = PaperDocumentRenderer._option_columns(options)
        if columns == 1:
            for index, option in enumerate(options):
                option_line = doc.add_paragraph(style="Normal")
                option_line.paragraph_format.left_indent = Inches(0.28)
                option_line.paragraph_format.space_after = Pt(1)
                option_line.add_run(f"({chr(65 + index)}) ")
                _append_latex_content(option_line, str(option))
            return
        rows = (len(options) + columns - 1) // columns
        table = doc.add_table(rows=rows, cols=columns)
        table.style = "Table Grid"
        # Bordered grid, like printed JEE sheets: every option sits in a cell.
        for row in table.rows:
            for cell in row.cells:
                _set_cell_borders(cell, visible=True)
                _set_cell_padding(cell, 60)
        for index, option in enumerate(options):
            cell = table.cell(index // columns, index % columns)
            cell.text = ""
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(1)
            paragraph.add_run(f"({chr(65 + index)}) ")
            _append_latex_content(paragraph, str(option))
        doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def _add_answer_key(self, doc: Document, paper: dict[str, Any]) -> None:
        doc.add_paragraph("Answer Key", style="Heading 1")
        table = doc.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        for index, header in enumerate(("Q", "Answer", "Marks", "Concept")):
            cell = table.cell(0, index)
            cell.text = header
            _set_cell_padding(cell)
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in cell.paragraphs[0].runs:
                run.font.bold = True
        for number, question in enumerate(paper["questions"], start=1):
            payload = question["question_json"]
            answer = (question.get("answer_json") or {}).get("correct_answer") or "Not verified"
            values = (str(number), str(payload.get("marks") or ""), str(payload.get("primary_concept") or ""))
            row = table.add_row().cells
            answer_cell = row[1]
            _set_cell_padding(answer_cell)
            answer_cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            _append_latex_content(answer_cell.paragraphs[0], str(answer))
            for index, value in ((0, values[0]), (2, values[1]), (3, values[2])):
                cell = row[index]
                cell.text = value
                _set_cell_padding(cell)
                cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER if index < 3 else WD_ALIGN_PARAGRAPH.LEFT
        solutions = [item for item in paper["questions"] if item.get("solution")]
        if solutions:
            doc.add_paragraph("Solutions", style="Heading 1")
            for number, question in enumerate(paper["questions"], start=1):
                if question.get("solution"):
                    solution = doc.add_paragraph()
                    solution.add_run(f"{number}. ")
                    _append_latex_content(solution, str(question["solution"]))

    @staticmethod
    def _latex_escape(value: str) -> str:
        return (
            str(value)
            .replace("\\", r"\textbackslash{}")
            .replace("&", r"\&").replace("%", r"\%").replace("#", r"\#")
            .replace("_", r"\_").replace("{", r"\{").replace("}", r"\}")
            .replace("~", r"\textasciitilde{}").replace("^", r"\textasciicircum{}")
        )

    @staticmethod
    def _latex_math(value: str) -> str:
        """Pass question LaTeX straight to LaTeX — same fidelity as KaTeX UI."""
        text = _normalize_latex(str(value or ""))
        # Generation pipelines emit \(...\) / \[...\] which LaTeX understands
        # natively; bare \(...\) inside $...$ would break, so keep as-is.
        return text

    def _build_pdf_via_latex(self, paper: dict[str, Any], variant: ExportVariant, stem: str) -> Path:
        pdflatex = shutil.which("pdflatex")
        if not pdflatex:
            raise DocumentRenderError("LaTeX pdflatex is not installed on the server.")
        tex_path = self.output_root / f"{stem}.tex"
        pdf_path = self.output_root / f"{stem}.pdf"
        tex_path.write_text(self._latex_source(paper, variant), encoding="utf-8")
        for _ in range(2):  # second pass resolves page references/footer
            process = subprocess.run(
                [pdflatex, "-interaction=nonstopmode", "-halt-on-error", "-output-directory", str(self.output_root), str(tex_path)],
                check=False, capture_output=True, text=True, timeout=90,
            )
            if process.returncode != 0:
                log = (process.stdout + process.stderr)[-3000:]
                raise DocumentRenderError(f"LaTeX PDF export failed: {log.strip()}")
        if not pdf_path.exists() or pdf_path.stat().st_size == 0:
            raise DocumentRenderError("LaTeX PDF export failed: empty output.")
        # Remove auxiliary files, keep tex for debugging.
        for suffix in (".aux", ".log", ".out"):
            aux = self.output_root / f"{stem}{suffix}"
            if aux.exists():
                aux.unlink(missing_ok=True)
        return pdf_path

    def _latex_source(self, paper: dict[str, Any], variant: ExportVariant) -> str:
        branding = paper.get("branding_config") or {}
        institution = self._latex_escape(branding.get("institution_name") or "")
        address = self._latex_escape(str(branding.get("address") or "").strip())
        contact = self._latex_escape(str(branding.get("contact") or "").strip())
        header_text = self._latex_escape(str(branding.get("header_text") or branding.get("institution_name") or "Question Paper"))
        footer_text = self._latex_escape(str(branding.get("footer_text") or "").strip())
        title = self._latex_escape(str(paper["title"])) + (" --- ANSWER KEY" if variant == ExportVariant.ANSWER_KEY else "")
        exam = self._latex_escape(str(paper.get("exam") or ""))
        subject = self._latex_escape(str(paper.get("subject") or ""))
        marks = branding.get("total_marks")
        if marks in (None, ""):
            marks = sum(int((q.get("question_json") or {}).get("marks") or 0) for q in paper["questions"])
        duration = branding.get("duration_minutes")
        duration_text = self._format_duration(duration) if duration not in (None, "") else "2 : 30 hours"
        instructions = branding.get("instructions") or [
            "Read every question carefully before selecting an answer.",
            "For single-correct questions, mark one option only.",
            "Use the answer sheet or space provided by the invigilator.",
        ]
        lines = [
            r"\documentclass[11pt,a4paper]{article}",
            r"\usepackage[margin=19mm,top=17mm,bottom=17mm]{geometry}",
            r"\usepackage{amsmath,amssymb,amsfonts}",
            r"\usepackage{mathptmx}",
            r"\usepackage{enumitem}",
            r"\usepackage{fancyhdr}",
            r"\usepackage{array,tabularx,booktabs}",
            r"\usepackage[hidelinks]{hyperref}",
            r"\setlength{\parindent}{0pt}\setlength{\parskip}{4pt}",
            r"\setlist[enumerate,1]{leftmargin=1.1em,itemsep=3pt,parsep=2pt}",
            r"\setlist[itemize]{leftmargin=1.4em,itemsep=1pt}",
            r"\pagestyle{fancy}\fancyhf{}",
            rf"\fancyhead[C]{{\footnotesize \textbf{{{header_text}}}}}",
            rf"\fancyfoot[C]{{\footnotesize {footer_text + r'  $\cdot$  ' if footer_text else ''}Page \thepage}}",
            r"\renewcommand{\headrulewidth}{0.4pt}",
            r"\begin{document}",
        ]
        if institution:
            lines.append(rf"{{\centering \large \textbf{{{institution}}}\par}}")
        if address:
            lines.append(rf"{{\centering \small \textit{{{address}}}\par}}")
        if contact and contact.strip():
            lines.append(rf"{{\centering \footnotesize {contact}\par}}")
        lines += [
            r"\vspace{2mm}",
            rf"\noindent \textbf{{Marks : {self._latex_escape(marks)}}} \hfill \textbf{{Time : {self._latex_escape(duration_text)}}}",
            r"\noindent\rule{\linewidth}{1.1pt}\vspace{-1mm}\noindent\rule{\linewidth}{0.5pt}",
            rf"{{\centering \Large \textbf{{{title.upper()}}}\par}}",
            rf"{{\centering {exam} $|$ {subject}\par}}",
            r"\noindent\rule{\linewidth}{1.1pt}\vspace{-1mm}\noindent\rule{\linewidth}{0.5pt}",
            r"\vspace{1mm}",
            rf"\noindent \textbf{{Duration:}} {self._latex_escape(self._format_duration(duration) if duration not in (None, '') else 'Not specified')} \quad \textbf{{Total Marks:}} {self._latex_escape(marks)} \quad \textbf{{Questions:}} {len(paper['questions'])}\par",
            r"\vspace{2mm}",
            "",
        ]
        if variant == ExportVariant.QUESTION_PAPER:
            lines += [
                r"\begin{tabularx}{\linewidth}{|X|X|}\hline",
                r"Candidate Name: \rule{6cm}{0.4pt} & Roll Number: \rule{3.5cm}{0.4pt} \\\hline",
                r"\end{tabularx}",
                "",
                r"\textbf{Instructions}",
                r"\begin{itemize}[topsep=2pt]",
                *[rf"\item {self._latex_escape(item)}" for item in instructions],
                r"\end{itemize}",
            ]
        else:
            lines.append(r"\section*{Answer Key}")
            lines.append(r"\noindent\begin{tabularx}{\linewidth}{|c|c|c|X|}\hline")
            lines.append(r"\textbf{Q} & \textbf{Answer} & \textbf{Marks} & \textbf{Concept} \\\hline")
            for number, question in enumerate(paper["questions"], start=1):
                payload = question.get("question_json") or {}
                answer = (question.get("answer_json") or {}).get("correct_answer") or "Not verified"
                concept = self._latex_escape(str(payload.get("primary_concept") or ""))
                marks_q = self._latex_escape(str(payload.get("marks") or ""))
                answer_tex = self._latex_math(answer)
                lines.append(rf"{number} & {answer_tex} & {marks_q} & {concept} \\\hline")
            lines.append(r"\end{tabularx}")
            lines.append("")
            solutions = [q for q in paper["questions"] if q.get("solution")]
            if solutions:
                lines.append(r"\section*{Solutions}")
                lines.append(r"\begin{enumerate}")
                for number, question in enumerate(paper["questions"], start=1):
                    if question.get("solution"):
                        lines.append(rf"\item {self._latex_math(question['solution'])}")
                lines.append(r"\end{enumerate}")
            lines.append(r"\end{document}")
            return "\n".join(lines)
        # Group questions by section, preserving paper order.
        sections = {s["id"]: s["title"] for s in paper.get("sections", [])}
        order = [s["id"] for s in paper.get("sections", [])] + [None]
        grouped: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        for question in paper["questions"]:
            grouped[question.get("section_id")].append(question)
        number = 1
        for section_id in order:
            items = sorted(grouped.get(section_id, []), key=lambda item: item["position"])
            if not items:
                continue
            if section_id is not None:
                lines.append(rf"\section*{{{self._latex_escape(sections.get(section_id, 'Section'))}}}")
            elif order != [None]:
                lines.append(r"\section*{Unsectioned questions}")
            lines.append(r"\begin{enumerate}[resume]")
            for question in items:
                payload = question.get("question_json") or {}
                stem = self._latex_math(payload.get("stem", ""))
                marks_q = payload.get("marks")
                marks_suffix = f" \\hfill [{self._latex_escape(marks_q)} marks]" if marks_q else ""
                lines.append(rf"\item {stem}{marks_suffix}")
                options = list(payload.get("options") or [])
                if options:
                    lines.append(self._latex_options(options))
            lines.append(r"\end{enumerate}")
        lines.append(r"\end{document}")
        return "\n".join(lines)

    @staticmethod
    def _option_columns(options: list[str]) -> int:
        """Grid width shared by DOCX and PDF so both exports position alike."""
        lengths = [_plain_length(option) for option in options]
        if len(options) == 4 and max(lengths, default=0) <= 14:
            return 4
        if len(options) == 4 and max(lengths, default=0) <= 42:
            return 2
        if len(options) == 2 and max(lengths, default=0) <= 42:
            return 2
        return 1

    @staticmethod
    def _latex_options(options: list[str]) -> str:
        cols = PaperDocumentRenderer._option_columns(options)
        if cols == 1:
            return r"\begin{enumerate}[label=(\Alph*),leftmargin=1.6em,itemsep=1pt]" + " ".join(
                rf"\item {PaperDocumentRenderer._latex_math(option)}" for option in options
            ) + r"\end{enumerate}"
        # Borderless full-width grid, positioned exactly like the DOCX export:
        # short options 4-across, medium options 2x2. No box lines — only
        # alignment. Rows breathe so stacked fractions never collide.
        col_spec = " ".join(["X"] * cols)
        rows = []
        for start in range(0, len(options), cols):
            chunk = options[start:start + cols]
            cells = " & ".join(
                rf"({chr(65 + start + i)}) \quad {PaperDocumentRenderer._latex_math(opt)}"
                for i, opt in enumerate(chunk)
            )
            cells += " & " * (cols - len(chunk))
            rows.append(cells.rstrip(" & ") + r" \\[10pt]")
        return (
            r"{\renewcommand{\arraystretch}{1.8}"
            + "\n" + rf"\begin{{tabularx}}{{\linewidth}}{{{col_spec}}}" + "\n" + "\n".join(rows) + "\n" + r"\end{tabularx}}"
        )

    @staticmethod
    def _convert_to_pdf(docx_path: Path) -> Path:
        office = shutil.which("soffice") or "/home/excel/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice"
        if not Path(office).exists():
            raise DocumentRenderError("PDF export requires LibreOffice or soffice on the server.")
        process = subprocess.run([office, "--headless", "--convert-to", "pdf", "--outdir", str(docx_path.parent), str(docx_path)], check=False, capture_output=True, text=True, timeout=60)
        pdf_path = docx_path.with_suffix(".pdf")
        if process.returncode != 0 or not pdf_path.exists() or pdf_path.stat().st_size == 0:
            raise DocumentRenderError(f"PDF export failed: {process.stderr.strip() or process.stdout.strip()}")
        return pdf_path
