"""文档元数据提取模块。

从首页提取法规/判决书的元数据：标题、文号、日期、机关等。
"""

from __future__ import annotations

import logging

from src.models import DocType, LawMeta, LineMeta
from src.patterns import (
    RE_AUTHORITY,
    RE_CASE_NUMBER,
    RE_DATE,
    RE_DOC_ID,
    RE_JUDGMENT_TITLE,
    detect_doc_type,
)

logger = logging.getLogger(__name__)


def extract_meta_from_page(
    meta: LawMeta,
    page_lines: list[LineMeta],
    ocr_fallback_text: str = "",
) -> None:
    """从首页提取文档元数据，自动检测文档类型。"""
    # 优先使用已提取的行文本，避免重复调用 page.extract_text()
    text = "\n".join(line.text for line in page_lines)

    # pdfplumber 无文字时使用 OCR 文本回退
    if not text and ocr_fallback_text:
        text = ocr_fallback_text
        logger.debug("对元数据提取使用 OCR 回退文本")

    # ── 文档类型检测 ──
    meta.doc_type = DocType(detect_doc_type(text))

    # ── 标题提取（相对字号：取页面最大字号行作为标题） ──
    if page_lines:
        max_font_size = max(
            (line.font_size for line in page_lines if line.font_size > 0),
            default=0,
        )
        # 标题行：字号 >= 页面最大字号的 90%（容差），且文本长度 > 4
        title_candidates = [
            line.text for line in page_lines
            if line.font_size >= max_font_size * 0.9
            and line.font_size > 0
            and len(line.text) > 4
        ]
        if title_candidates:
            meta.name = title_candidates[0]

    # ── 文号提取 ──
    for m in RE_DOC_ID.finditer(text):
        meta.doc_id = m.group(0).strip()
        break

    # ── 日期提取 ──
    dates = RE_DATE.findall(text)
    if dates:
        meta.publish_date = dates[0].strip()
        if len(dates) > 1:
            meta.effective_date = dates[1].strip()

    # ── 制定机关提取 ──
    for m in RE_AUTHORITY.finditer(text):
        meta.issuing_authority = m.group(0).strip()
        break

    # ── 判决书特有元数据 ──
    if meta.doc_type == DocType.JUDGMENT:
        _extract_judgment_meta(meta, text, page_lines)


def _extract_judgment_meta(
    meta: LawMeta,
    text: str,
    page_lines: list[LineMeta],
) -> None:
    """从判决书首页提取特有元数据。"""
    # 案号
    for m in RE_CASE_NUMBER.finditer(text):
        meta.extra["case_number"] = m.group(0).strip()
        break

    # 法院名称和文书类型
    for m in RE_JUDGMENT_TITLE.finditer(text):
        court = m.group(2)
        case_type = m.group(3)
        doc_type_name = m.group(4)
        meta.extra["court"] = court
        meta.extra["judgment_type"] = f"{case_type}{doc_type_name}"
        break

    # 裁判日期（取最后一个日期）
    dates = RE_DATE.findall(text)
    if dates:
        meta.extra["judgment_date"] = dates[-1].strip()
