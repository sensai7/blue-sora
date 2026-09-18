"""Deterministic, searchable PDF generation for Blue Sora works."""

from __future__ import annotations

import hashlib
import html
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from PIL import Image as PillowImage
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.textsplit import ALL_CANNOT_END, ALL_CANNOT_START
from reportlab.platypus import (
    CondPageBreak,
    Image,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    Flowable,
)

from blue_sora.ingestion import canonical_text


PDF_GENERATOR_VERSION = "blue-sora-pdf-v3"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "biz-ud-mincho" / "BIZUDMincho-Regular.ttf"
FONT_LICENSE_PATH = PROJECT_ROOT / "assets" / "fonts" / "biz-ud-mincho" / "OFL.txt"
FONT_NAME = "BIZUDMincho"
PAGE_BREAK_MARKERS = {"［＃改ページ］", "［＃改丁］", "［＃改見開き］"}


class JapaneseParagraph(Paragraph):
    """Work around ReportLab's CJK splitter treating inline images as empty glyphs."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for fragment in self.frags:
            if not getattr(fragment, "text", None) and hasattr(fragment, "cbDefn"):
                fragment.text = "\ufffc"


@dataclass(frozen=True)
class InlineToken:
    """One indivisible unit in a ruby-aware line."""

    kind: str
    text: str = ""
    reading: str = ""
    path: Path | None = None
    children: tuple[InlineToken, ...] = ()
    width: float = 0
    height: float = 0
    font_size: float = 10.5
    y_offset: float = 0

    @property
    def first_character(self) -> str:
        return (self.text or self.reading)[:1]

    @property
    def last_character(self) -> str:
        return (self.text or self.reading)[-1:]


@dataclass
class RubyLine:
    tokens: list[InlineToken]
    indent: float
    height: float


class RubyParagraph(Flowable):
    """A selectable-text paragraph with readings centered above base words."""

    ruby_font_size = 5.0
    ruby_gap = 1.0

    def __init__(
        self,
        tokens: list[InlineToken],
        style: ParagraphStyle,
        *,
        fixed_lines: list[RubyLine] | None = None,
    ) -> None:
        super().__init__()
        self.tokens = tokens
        self.style = style
        self._fixed_lines = fixed_lines
        self._lines: list[RubyLine] = []
        self.spaceBefore = style.spaceBefore
        self.spaceAfter = style.spaceAfter
        self.keepWithNext = getattr(style, "keepWithNext", False)

    @staticmethod
    def _line_height(tokens: list[InlineToken], leading: float) -> float:
        content_height = max((token.height for token in tokens if token.kind == "image"), default=0)
        if any(token.kind == "ruby" for token in tokens):
            content_height = max(content_height, 10.5 + RubyParagraph.ruby_gap + RubyParagraph.ruby_font_size + 1.5)
        return max(leading, content_height)

    def _layout(self, available_width: float) -> list[RubyLine]:
        lines: list[RubyLine] = []
        current: list[InlineToken] = []
        first_line = True
        indent = float(self.style.firstLineIndent or 0)
        used = 0.0

        def finish_line() -> None:
            nonlocal current, first_line, indent, used
            while current and current[-1].kind == "text" and current[-1].text.isspace():
                current.pop()
            lines.append(RubyLine(current, indent, self._line_height(current, self.style.leading)))
            current = []
            first_line = False
            indent = 0.0
            used = 0.0

        for token in self.tokens:
            if token.kind == "break":
                finish_line()
                continue
            limit = max(1.0, available_width - indent)
            if current and used + token.width > limit:
                # Japanese closing punctuation belongs to the preceding line even
                # if that creates a very small optical overhang.
                if token.first_character in ALL_CANNOT_START:
                    current.append(token)
                    used += token.width
                    finish_line()
                    continue
                carry: list[InlineToken] = []
                while len(current) > 1 and current[-1].last_character in ALL_CANNOT_END:
                    carry.insert(0, current.pop())
                finish_line()
                current.extend(carry)
                used = sum(item.width for item in current)
            if not current and token.kind == "text" and token.text.isspace():
                continue
            current.append(token)
            used += token.width
        if current or not lines:
            finish_line()
        return lines

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        self.width = available_width
        self._lines = self._fixed_lines if self._fixed_lines is not None else self._layout(available_width)
        self.height = sum(line.height for line in self._lines)
        return self.width, self.height

    def split(self, available_width: float, available_height: float) -> list[Flowable]:
        self.wrap(available_width, available_height)
        used = 0.0
        split_at = 0
        for line in self._lines:
            if used + line.height > available_height + 0.01:
                break
            used += line.height
            split_at += 1
        if split_at == 0 or split_at == len(self._lines):
            return []
        first = RubyParagraph(self.tokens, self.style, fixed_lines=self._lines[:split_at])
        second = RubyParagraph(self.tokens, self.style, fixed_lines=self._lines[split_at:])
        first.spaceBefore = self.spaceBefore
        first.spaceAfter = 0
        first.keepWithNext = False
        second.spaceBefore = 0
        second.spaceAfter = self.spaceAfter
        second.keepWithNext = self.keepWithNext
        return [first, second]

    def draw(self) -> None:
        cursor = self.height
        base_size = float(self.style.fontSize)
        for line in self._lines:
            bottom = cursor - line.height
            has_ruby = any(token.kind == "ruby" for token in line.tokens)
            baseline = bottom + (1.5 if has_ruby else max(1.5, (line.height - base_size) / 2))
            x = line.indent
            for token in line.tokens:
                if token.kind == "image" and token.path is not None:
                    self.canv.drawImage(
                        str(token.path), x, bottom + (line.height - token.height) / 2,
                        width=token.width, height=token.height, mask="auto",
                    )
                elif token.kind == "ruby":
                    base_width = pdfmetrics.stringWidth(token.text, FONT_NAME, base_size)
                    reading_width = pdfmetrics.stringWidth(token.reading, FONT_NAME, self.ruby_font_size)
                    self.canv.setFillColor(self.style.textColor)
                    self.canv.setFont(FONT_NAME, base_size)
                    self.canv.drawString(x + (token.width - base_width) / 2, baseline, token.text)
                    self.canv.setFillColor(colors.HexColor("#374151"))
                    self.canv.setFont(FONT_NAME, self.ruby_font_size)
                    self.canv.drawString(
                        x + (token.width - reading_width) / 2,
                        baseline + base_size + self.ruby_gap,
                        token.reading,
                    )
                else:
                    self.canv.setFillColor(self.style.textColor)
                    self.canv.setFont(FONT_NAME, token.font_size)
                    self.canv.drawString(x, baseline + token.y_offset, token.text)
                x += token.width
            cursor = bottom


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def register_font() -> TTFont:
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        font = TTFont(FONT_NAME, str(FONT_PATH), validate=1)
        pdfmetrics.registerFont(font)
        pdfmetrics.registerFontFamily(
            FONT_NAME,
            normal=FONT_NAME,
            bold=FONT_NAME,
            italic=FONT_NAME,
            boldItalic=FONT_NAME,
        )
    return pdfmetrics.getFont(FONT_NAME)


def pdf_styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "BlueSoraTitle", parent=sample["Title"], fontName=FONT_NAME,
            fontSize=24, leading=36, alignment=TA_CENTER, textColor=colors.HexColor("#111827"),
            spaceAfter=12 * mm,
        ),
        "author": ParagraphStyle(
            "BlueSoraAuthor", parent=sample["Normal"], fontName=FONT_NAME,
            fontSize=12, leading=20, alignment=TA_CENTER, textColor=colors.HexColor("#374151"),
        ),
        "metadata": ParagraphStyle(
            "BlueSoraMetadata", parent=sample["Normal"], fontName=FONT_NAME,
            fontSize=8.5, leading=14, alignment=TA_CENTER, textColor=colors.HexColor("#4b5563"),
        ),
        "h2": ParagraphStyle(
            "BlueSoraH2", parent=sample["Heading2"], fontName=FONT_NAME,
            fontSize=16, leading=25, textColor=colors.HexColor("#111827"),
            spaceBefore=4 * mm, spaceAfter=4 * mm, keepWithNext=True, wordWrap="CJK",
        ),
        "h3": ParagraphStyle(
            "BlueSoraH3", parent=sample["Heading3"], fontName=FONT_NAME,
            fontSize=13, leading=21, textColor=colors.HexColor("#1f2937"),
            spaceBefore=4 * mm, spaceAfter=3 * mm, keepWithNext=True, wordWrap="CJK",
        ),
        "h4": ParagraphStyle(
            "BlueSoraH4", parent=sample["Heading4"], fontName=FONT_NAME,
            fontSize=11.5, leading=19, textColor=colors.HexColor("#374151"),
            spaceBefore=3 * mm, spaceAfter=2 * mm, keepWithNext=True, wordWrap="CJK",
        ),
        "body": ParagraphStyle(
            "BlueSoraBody", parent=sample["BodyText"], fontName=FONT_NAME,
            fontSize=10.5, leading=18, alignment=TA_LEFT, textColor=colors.HexColor("#111827"),
            firstLineIndent=10.5, spaceAfter=2.5 * mm, wordWrap="CJK",
            splitLongWords=True, allowWidows=0, allowOrphans=0,
        ),
        "note": ParagraphStyle(
            "BlueSoraNote", parent=sample["BodyText"], fontName=FONT_NAME,
            fontSize=8.5, leading=14, textColor=colors.HexColor("#374151"),
            spaceAfter=2 * mm, wordWrap="CJK", splitLongWords=True,
        ),
    }


def visible_text(value: Any) -> str:
    if isinstance(value, list):
        return "".join(visible_text(item) for item in value)
    if not isinstance(value, dict):
        return ""
    node_type = value.get("type")
    if node_type == "text":
        return value.get("text", "")
    if node_type == "ruby":
        return visible_text(value.get("base", [])) + value.get("reading", "")
    if node_type in {"paragraph", "heading"}:
        return visible_text(value.get("inlines", []))
    if node_type in {"emphasis", "warichu", "note", "anchor", "small", "subscript", "superscript", "styled", "source_markup"}:
        return visible_text(value.get("children", []))
    if node_type == "list":
        return visible_text(value.get("items", [])) + visible_text(value.get("supplemental", []))
    if node_type == "table":
        return visible_text(value.get("rows", []))
    if node_type == "styled_block":
        return visible_text(value.get("blocks", []))
    return ""


def preflight_glyphs(text: str) -> None:
    font = register_font()
    missing = sorted({character for character in text if not character.isspace() and ord(character) not in font.face.charToGlyph})
    if missing:
        codepoints = ", ".join(f"U+{ord(character):04X}" for character in missing[:20])
        raise ValueError(f"BIZ UD Mincho is missing required glyphs: {codepoints}")


def image_dimensions(path: Path, max_width: float, max_height: float) -> tuple[float, float]:
    with PillowImage.open(path) as image:
        width, height = image.size
    scale = min(max_width / max(width, 1), max_height / max(height, 1), 1.0)
    return width * scale, height * scale


def render_inlines(nodes: Iterable[dict[str, Any]], assets: dict[str, Path]) -> str:
    output: list[str] = []
    for node in nodes:
        node_type = node.get("type")
        if node_type == "text":
            output.append(html.escape(node.get("text", "")))
        elif node_type == "line_break":
            output.append("<br/>")
        elif node_type == "ruby":
            base = render_inlines(node.get("base", []), assets)
            reading = html.escape(node.get("reading", ""))
            output.append(f'{base}<super><font size="5">{reading}</font></super>')
        elif node_type in {"illustration", "gaiji"}:
            path = assets.get(node.get("asset_id", ""))
            label = node.get("alt") or ("Illustration" if node_type == "illustration" else "Gaiji")
            if path and path.is_file():
                if node_type == "gaiji":
                    width = height = 10.5
                else:
                    width, height = image_dimensions(path, 60, 72)
                output.append(
                    f'<img src="{html.escape(path.as_posix(), quote=True)}" width="{width:.2f}" '
                    f'height="{height:.2f}" valign="middle"/>'
                )
            else:
                output.append(f'[{html.escape(label)} unavailable]')
        elif node_type == "emphasis":
            output.append(f'<b>{render_inlines(node.get("children", []), assets)}</b>')
        elif node_type in {"warichu", "note", "styled", "source_markup"}:
            output.append(render_inlines(node.get("children", []), assets))
        elif node_type == "anchor":
            output.append(render_inlines(node.get("children", []), assets))
        elif node_type in {"small", "subscript", "superscript"}:
            tag = {"small": "font", "subscript": "sub", "superscript": "super"}[node_type]
            attrs = ' size="8"' if tag == "font" else ""
            output.append(f'<{tag}{attrs}>{render_inlines(node.get("children", []), assets)}</{tag}>')
    return "".join(output)


def contains_ruby(nodes: Iterable[dict[str, Any]]) -> bool:
    for node in nodes:
        if node.get("type") == "ruby":
            return True
        for key in ("children", "base"):
            children = node.get(key, [])
            if children and contains_ruby(children):
                return True
    return False


def text_tokens(text: str, font_size: float, y_offset: float = 0) -> list[InlineToken]:
    tokens: list[InlineToken] = []
    # Keep Latin words together; Japanese characters remain natural break points.
    for part in re.findall(r"\r\n|\r|\n|[\t ]+|[\x21-\x7e]+|[^\x00-\x7f]", text):
        if part in {"\r", "\n", "\r\n"}:
            tokens.append(InlineToken("break"))
        else:
            tokens.append(InlineToken(
                "text", text=part, width=pdfmetrics.stringWidth(part, FONT_NAME, font_size),
                font_size=font_size, y_offset=y_offset,
            ))
    return tokens


def ruby_tokens(
    nodes: Iterable[dict[str, Any]],
    assets: dict[str, Path],
    *,
    font_size: float = 10.5,
    y_offset: float = 0,
) -> list[InlineToken]:
    tokens: list[InlineToken] = []
    for node in nodes:
        node_type = node.get("type")
        if node_type == "text":
            tokens.extend(text_tokens(node.get("text", ""), font_size, y_offset))
        elif node_type == "line_break":
            tokens.append(InlineToken("break"))
        elif node_type == "ruby":
            base_nodes = node.get("base", [])
            base = visible_text(base_nodes)
            base_tokens = tuple(ruby_tokens(base_nodes, assets, font_size=font_size))
            reading = node.get("reading", "")
            width = max(
                sum(token.width for token in base_tokens),
                pdfmetrics.stringWidth(reading, FONT_NAME, RubyParagraph.ruby_font_size),
            )
            tokens.append(InlineToken(
                "ruby", text=base, reading=reading, children=base_tokens,
                width=width, font_size=font_size,
                height=font_size + RubyParagraph.ruby_gap + RubyParagraph.ruby_font_size + 1.5,
            ))
        elif node_type in {"illustration", "gaiji"}:
            path = assets.get(node.get("asset_id", ""))
            if path and path.is_file():
                if node_type == "gaiji":
                    width = height = font_size
                else:
                    width, height = image_dimensions(path, 60, 72)
                tokens.append(InlineToken("image", path=path, width=width, height=height))
            else:
                label = node.get("alt") or ("Illustration" if node_type == "illustration" else "Gaiji")
                tokens.extend(text_tokens(f"[{label} unavailable]", font_size, y_offset))
        elif node_type == "small":
            tokens.extend(ruby_tokens(node.get("children", []), assets, font_size=8, y_offset=y_offset))
        elif node_type == "superscript":
            tokens.extend(ruby_tokens(node.get("children", []), assets, font_size=8, y_offset=y_offset + 3))
        elif node_type == "subscript":
            tokens.extend(ruby_tokens(node.get("children", []), assets, font_size=8, y_offset=y_offset - 2))
        elif node_type in {"emphasis", "warichu", "note", "styled", "source_markup", "anchor"}:
            tokens.extend(ruby_tokens(node.get("children", []), assets, font_size=font_size, y_offset=y_offset))
    return tokens


def image_flowable(node: dict[str, Any], assets: dict[str, Path]) -> Image | Paragraph:
    path = assets.get(node.get("asset_id", ""))
    label = node.get("alt") or "Illustration"
    if not path or not path.is_file():
        return Paragraph(f'[{html.escape(label)} unavailable]', pdf_styles()["note"])
    width, height = image_dimensions(path, 105 * mm, 140 * mm)
    image = Image(str(path), width=width, height=height)
    image.hAlign = "CENTER"
    return image


def paragraph_from_inlines(
    inlines: list[dict[str, Any]], style: ParagraphStyle, assets: dict[str, Path]
) -> JapaneseParagraph | RubyParagraph | Image:
    if len(inlines) == 1 and inlines[0].get("type") == "illustration":
        return image_flowable(inlines[0], assets)
    if contains_ruby(inlines):
        return RubyParagraph(ruby_tokens(inlines, assets, font_size=float(style.fontSize)), style)
    markup = render_inlines(inlines, assets) or "&#160;"
    return JapaneseParagraph(markup, style)


def flowables_for_blocks(
    blocks: Iterable[dict[str, Any]],
    assets: dict[str, Path],
    styles: dict[str, ParagraphStyle],
    *,
    heading_state: dict[str, int] | None = None,
) -> list[Any]:
    heading_state = heading_state if heading_state is not None else {"number": 0, "h2": 0, "outline": -1}
    story: list[Any] = []
    for block in blocks:
        block_type = block.get("type")
        if block_type == "heading":
            level = min(4, max(2, int(block.get("level", 2))))
            if level == 2:
                heading_state["h2"] += 1
                if heading_state["h2"] > 1:
                    story.append(PageBreak())
            heading_state["number"] += 1
            label = canonical_text(block) or f"Section {heading_state['number']}"
            paragraph = paragraph_from_inlines(block.get("inlines", []), styles[f"h{level}"], assets)
            if isinstance(paragraph, (JapaneseParagraph, RubyParagraph)):
                outline_level = min(level - 2, heading_state["outline"] + 1)
                heading_state["outline"] = outline_level
                paragraph._bookmark_name = f"section-{heading_state['number']}"  # type: ignore[attr-defined]
                paragraph._outline_title = label  # type: ignore[attr-defined]
                paragraph._outline_level = outline_level  # type: ignore[attr-defined]
            story.extend([CondPageBreak(30 * mm), paragraph])
        elif block_type == "paragraph":
            if canonical_text(block).strip() in PAGE_BREAK_MARKERS:
                story.append(PageBreak())
            else:
                story.append(paragraph_from_inlines(block.get("inlines", []), styles["body"], assets))
        elif block_type == "separator":
            story.append(Spacer(1, 5 * mm))
        elif block_type == "list":
            items = []
            for item in block.get("items", []):
                item_flowables = flowables_for_blocks(item, assets, styles, heading_state=heading_state)
                items.append(ListItem(item_flowables, leftIndent=4 * mm))
            if items:
                story.append(ListFlowable(items, bulletType="1" if block.get("ordered") else "bullet", leftIndent=8 * mm))
            story.extend(flowables_for_blocks(block.get("supplemental", []), assets, styles, heading_state=heading_state))
        elif block_type == "table":
            rows = []
            for row in block.get("rows", []):
                rows.append([
                    flowables_for_blocks(cell, assets, styles, heading_state=heading_state) or [JapaneseParagraph("&#160;", styles["body"])]
                    for cell in row
                ])
            if rows:
                table = Table(rows, repeatRows=1, hAlign="LEFT")
                table.setStyle(TableStyle([
                    ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9ca3af")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(table)
        elif block_type == "styled_block":
            story.extend(flowables_for_blocks(block.get("blocks", []), assets, styles, heading_state=heading_state))
    return story


class BlueSoraDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, flowable: Any) -> None:
        bookmark = getattr(flowable, "_bookmark_name", None)
        if bookmark:
            self.canv.bookmarkPage(bookmark)
            self.canv.addOutlineEntry(
                getattr(flowable, "_outline_title", bookmark),
                bookmark,
                level=getattr(flowable, "_outline_level", 0),
                closed=False,
            )


class DeterministicCanvas(Canvas):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["invariant"] = 1
        kwargs["pageCompression"] = 1
        super().__init__(*args, **kwargs)


def draw_page(canvas: Canvas, doc: BlueSoraDocTemplate, title: str, *, first: bool = False) -> None:
    canvas.saveState()
    canvas.setFont(FONT_NAME, 7.5)
    canvas.setFillColor(colors.HexColor("#6b7280"))
    width, _ = A5
    if not first:
        canvas.drawString(doc.leftMargin, A5[1] - 12 * mm, title[:42])
        canvas.line(doc.leftMargin, A5[1] - 14 * mm, width - doc.rightMargin, A5[1] - 14 * mm)
    canvas.drawCentredString(width / 2, 9 * mm, str(canvas.getPageNumber()))
    canvas.restoreState()


def build_pdf(work: dict[str, Any], authors: list[dict[str, Any]], catalog_root: Path) -> bytes:
    register_font()
    styles = pdf_styles()
    title = work["title"]["display"]
    author_names = [author["name"]["display"] for author in authors]
    author_label = "・".join(author_names)
    asset_paths = {
        asset["id"]: catalog_root.parent / asset["build_path"]
        for asset in work["assets"]
        if asset.get("status") == "stored" and asset.get("build_path")
    }
    all_text = title + author_label + visible_text(list(work["content"].values()))
    preflight_glyphs(all_text)
    missing_assets = [path for path in asset_paths.values() if not path.is_file()]
    if missing_assets:
        raise FileNotFoundError(f"stored PDF asset is missing: {missing_assets[0]}")

    output = io.BytesIO()
    document = BlueSoraDocTemplate(
        output,
        pagesize=A5,
        leftMargin=17 * mm,
        rightMargin=17 * mm,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
        title=title,
        author=author_label,
        subject=f"Public-domain Japanese literature from Aozora Bunko - {work['source'].get('card_url') or ''}",
        creator=f"Blue Sora {PDF_GENERATOR_VERSION}",
        displayDocTitle=True,
    )
    source_url = work["source"].get("card_url") or ""
    story: list[Any] = [
        Spacer(1, 30 * mm),
        JapaneseParagraph(html.escape(title), styles["title"]),
        JapaneseParagraph(html.escape(author_label), styles["author"]),
        Spacer(1, 12 * mm),
        JapaneseParagraph(
            f'{html.escape(work.get("orthography") or "Orthography not recorded")}<br/>'
            f'Aozora work {html.escape(work["aozora_work_id"])}',
            styles["metadata"],
        ),
        Spacer(1, 35 * mm),
        JapaneseParagraph("Blue Sora · 青空文庫", styles["metadata"]),
        PageBreak(),
    ]
    body = work["content"].get("body", [])
    if not any(block.get("type") == "heading" for block in body):
        story.append(JapaneseParagraph("本文", styles["h2"]))
    story.extend(flowables_for_blocks(body, asset_paths, styles))

    notes = work["content"].get("notation_notes", [])
    bibliography = work["content"].get("bibliography", [])
    story.extend([PageBreak(), JapaneseParagraph("注記・底本情報", styles["h2"])])
    story.extend(flowables_for_blocks(notes, asset_paths, styles))
    story.extend(flowables_for_blocks(bibliography, asset_paths, styles))
    source_markup = html.escape(source_url, quote=True)
    story.extend([
        Spacer(1, 6 * mm),
        JapaneseParagraph(
            "This PDF was generated by Blue Sora from canonical Aozora Bunko content. "
            + (f'<link href="{source_markup}" color="#1d4ed8">Aozora Bunko source card</link>.' if source_url else ""),
            styles["note"],
        ),
        JapaneseParagraph(
            "Font: BIZ UD Mincho by the BIZ UDMincho Project Authors, embedded under the SIL Open Font License 1.1.",
            styles["note"],
        ),
    ])
    document.build(
        story,
        onFirstPage=lambda canvas, doc: draw_page(canvas, doc, title, first=True),
        onLaterPages=lambda canvas, doc: draw_page(canvas, doc, title),
        canvasmaker=DeterministicCanvas,
    )
    return output.getvalue()


def dereference(value: Any) -> Any:
    return value.get_object() if hasattr(value, "get_object") else value


def font_has_embedded_file(font: Any) -> bool:
    font = dereference(font)
    descendants = dereference(font.get("/DescendantFonts", []))
    candidates = [dereference(item) for item in descendants] if descendants else [font]
    return bool(candidates) and all(
        (descriptor := dereference(candidate.get("/FontDescriptor")))
        and any(descriptor.get(key) is not None for key in ("/FontFile", "/FontFile2", "/FontFile3"))
        for candidate in candidates
    )


def font_is_embedded(font: Any) -> bool:
    font = dereference(font)
    # ReportLab initializes each page with an unused Standard 14 Helvetica
    # resource before switching to the embedded Japanese font.
    if str(font.get("/BaseFont", "")) in {
        "/Courier", "/Courier-Bold", "/Courier-Oblique", "/Courier-BoldOblique",
        "/Helvetica", "/Helvetica-Bold", "/Helvetica-Oblique", "/Helvetica-BoldOblique",
        "/Times-Roman", "/Times-Bold", "/Times-Italic", "/Times-BoldItalic",
        "/Symbol", "/ZapfDingbats",
    }:
        return True
    return font_has_embedded_file(font)


def page_image_count(page: Any) -> int:
    resources = dereference(page.get("/Resources", {}))
    xobjects = dereference(resources.get("/XObject", {})) if resources else {}
    return sum(1 for value in xobjects.values() if dereference(value).get("/Subtype") == "/Image")


def validate_pdf_bytes(payload: bytes, work: dict[str, Any] | None = None) -> dict[str, int]:
    try:
        reader = PdfReader(io.BytesIO(payload))
    except Exception as error:
        raise ValueError(f"invalid PDF: {error}") from error
    if not reader.pages:
        raise ValueError("PDF has no pages")
    metadata = reader.metadata
    if work is not None and (metadata.title or "") != work["title"]["display"]:
        raise ValueError("PDF title metadata does not match work")
    extracted_pages = [(page.extract_text() or "") for page in reader.pages]
    extracted = "".join(extracted_pages)
    if not extracted.strip():
        raise ValueError("PDF text is not searchable")
    if "\ufffd" in extracted:
        raise ValueError("PDF text contains replacement glyphs")
    fonts_seen = 0
    embedded_fonts = 0
    for page in reader.pages:
        resources = dereference(page.get("/Resources", {}))
        fonts = dereference(resources.get("/Font", {})) if resources else {}
        for font in fonts.values():
            fonts_seen += 1
            if not font_is_embedded(font):
                raise ValueError("PDF contains a non-embedded font")
            embedded_fonts += int(font_has_embedded_file(font))
    if fonts_seen == 0:
        raise ValueError("PDF contains no font resources")
    if embedded_fonts == 0:
        raise ValueError("PDF does not embed its Japanese font")
    if work is not None:
        expected = "".join(canonical_text(section) for section in work["content"].values())
        for marker in PAGE_BREAK_MARKERS:
            expected = expected.replace(marker, "")
        expected_chars = {character for character in expected if not character.isspace()}
        missing_chars = expected_chars - set(extracted)
        if missing_chars:
            sample = "".join(sorted(missing_chars)[:20])
            raise ValueError(f"searchable PDF text is missing source characters: {sample}")
        if work["title"]["display"] not in extracted:
            raise ValueError("PDF searchable text is missing the title")
        if "Aozora Bunko" not in extracted:
            raise ValueError("PDF is missing source attribution")
        stored_images = [asset for asset in work["assets"] if asset.get("status") == "stored"]
        image_count = sum(page_image_count(page) for page in reader.pages)
        if stored_images and image_count == 0:
            raise ValueError("PDF is missing canonical images")
    else:
        image_count = sum(page_image_count(page) for page in reader.pages)
    return {"pages": len(reader.pages), "fonts": embedded_fonts, "images": image_count}


def validate_pdf(path: Path, work: dict[str, Any] | None = None) -> dict[str, int]:
    return validate_pdf_bytes(path.read_bytes(), work)


def work_fingerprint(work: dict[str, Any], authors: list[dict[str, Any]], font_hash: str) -> str:
    payload = json.dumps([PDF_GENERATOR_VERSION, font_hash, work, authors], ensure_ascii=False, sort_keys=True).encode("utf-8")
    return sha256_bytes(payload)


def write_bytes_if_changed(path: Path, payload: bytes) -> tuple[str, bool]:
    checksum = sha256_bytes(payload)
    if path.is_file() and path.read_bytes() == payload:
        return checksum, False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return checksum, True


def build_pdfs(catalog_dir: Path, output_dir: Path) -> dict[str, Any]:
    register_font()
    catalog = json.loads((catalog_dir / "indexes" / "catalog.json").read_text(encoding="utf-8"))
    author_index = json.loads((catalog_dir / "indexes" / "authors.json").read_text(encoding="utf-8"))
    authors = {author["id"]: author for author in author_index["authors"]}
    font_hash = sha256_bytes(FONT_PATH.read_bytes())
    manifest_path = output_dir / "pdf-manifest.json"
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    previous_outputs = previous.get("outputs", {})
    outputs: dict[str, dict[str, Any]] = {}
    download_dir = output_dir / "downloads"
    generated = 0
    unchanged = 0
    failed = 0
    expected: set[str] = set()
    for catalog_work in catalog["works"]:
        raw_id = catalog_work["id"].rsplit(":", 1)[-1]
        work = json.loads((catalog_dir / "works" / f"{raw_id}.json").read_text(encoding="utf-8"))
        work_authors = [authors[author_id] for author_id in work["author_ids"]]
        filename = f'{work["slug"]}.pdf'
        expected.add(filename)
        destination = download_dir / filename
        error_marker = download_dir / f"{filename}.error.txt"
        fingerprint = work_fingerprint(work, work_authors, font_hash)
        previous_record = previous_outputs.get(filename, {})
        if (
            destination.is_file()
            and previous_record.get("fingerprint") == fingerprint
            and previous_record.get("sha256") == sha256_bytes(destination.read_bytes())
        ):
            outputs[filename] = previous_record
            unchanged += 1
            continue
        try:
            payload = build_pdf(work, work_authors, catalog_dir)
            validation = validate_pdf_bytes(payload, work)
            checksum, changed = write_bytes_if_changed(destination, payload)
            if error_marker.is_file():
                error_marker.unlink()
            generated += int(changed)
            unchanged += int(not changed)
            outputs[filename] = {
                "fingerprint": fingerprint,
                "sha256": checksum,
                **validation,
            }
        except Exception as error:
            failed += 1
            if destination.is_file():
                destination.unlink()
            write_bytes_if_changed(error_marker, (str(error) + "\n").encode("utf-8"))
    if download_dir.is_dir():
        for path in download_dir.glob("*.pdf"):
            if path.name not in expected:
                path.unlink()
    manifest = {
        "schema_version": 1,
        "generator_version": PDF_GENERATOR_VERSION,
        "font": {
            "family": "BIZ UD Mincho",
            "sha256": font_hash,
            "license": "SIL Open Font License 1.1",
            "license_path": FONT_LICENSE_PATH.relative_to(PROJECT_ROOT).as_posix(),
        },
        "work_count": len(catalog["works"]),
        "failed": failed,
        "outputs": dict(sorted(outputs.items())),
    }
    write_bytes_if_changed(manifest_path, (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return {"works": len(catalog["works"]), "generated": generated, "unchanged": unchanged, "failed": failed}
