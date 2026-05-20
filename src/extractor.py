"""PDF 文本提取层。

封装 pdfplumber，提取文本的同时保留排版信息（坐标、字号、是否加粗），
用于后续的层级推断和结构识别。

用法:
    lines = extract_pdf("民法典.pdf")
    for line in lines:
        print(line.text, line.page_num, line.font_size)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Literal, Optional

from src.models import LawMeta, LineMeta
from src.patterns import RE_HEADER_FOOTER

_OcrMode = Literal["auto", "force", "off"]

logger = logging.getLogger(__name__)

# pdfplumber 单页字符数硬限制，超出自动跳过
_PAGE_CHAR_LIMIT = 200_000
_OCR_BATCH_SIZE = 5


def _process_pdf_page(
    page,
    page_num: int,
    pdf_path: Path,
    ocr_mode: _OcrMode,
    engine=None,
) -> tuple[list[LineMeta], str]:
    """处理单页 PDF，返回 (page_lines, ocr_fallback_text)。

    封装 OCR 决策、调用和回退逻辑，供 extract_pdf 复用。
    """
    # ── OCR 决策 ──
    use_ocr = False
    if ocr_mode == "force":
        use_ocr = True
    elif ocr_mode == "auto":
        from src.ocr import page_has_text

        use_ocr = not page_has_text(page)

    ocr_fallback_text = ""
    if use_ocr:
        try:
            from src.ocr import pdf_page_to_image

            if engine is None:
                from src.ocr import OcrEngine

                engine = OcrEngine.get_instance()

            image, effective_dpi = pdf_page_to_image(pdf_path, page_num - 1, dpi=300)
            page_lines = engine.ocr_page(image, page_num=page_num, dpi=effective_dpi)
            ocr_fallback_text = "\n".join(l.text for l in page_lines)
            logger.info("Page %d: OCR extracted %d lines", page_num, len(page_lines))
        except ImportError as e:
            logger.warning(
                "OCR 依赖未安装，第 %d 页回退到 pdfplumber: %s", page_num, e
            )
            page_lines = _extract_page_lines(page, page_num)
        except Exception as e:
            logger.error(
                "第 %d 页 OCR 失败，回退到 pdfplumber: %s", page_num, e
            )
            page_lines = _extract_page_lines(page, page_num)
    else:
        page_lines = _extract_page_lines(page, page_num)

    return page_lines, ocr_fallback_text


def extract_pdf(
    pdf_path: str | Path,
    *,
    max_pages: Optional[int] = None,
    filter_header_footer: bool = True,
    ocr_mode: _OcrMode = "off",
) -> tuple[list[LineMeta], LawMeta]:
    """提取 PDF 全文，返回 (lines, meta)。

    Parameters
    ----------
    pdf_path : str or Path
        PDF 文件路径。
    max_pages : int, optional
        最多处理多少页（用于快速预览）。
    filter_header_footer : bool
        是否过滤页眉页脚（默认 True）。
    ocr_mode : "auto" | "force" | "off"
        OCR 模式（默认 "off"）：
        - "auto"  → 仅对 pdfplumber 返回极少字符的页面使用 OCR
        - "force" → 所有页面强制 OCR
        - "off"   → 不使用 OCR（向后兼容）

    Returns
    -------
    lines : list[LineMeta]
        按页码+坐标排序的文本行。
    meta : LawMeta
        从第一页提取的法规元数据。
    """
    import pdfplumber

    pdf_path = Path(pdf_path)
    lines: list[LineMeta] = []
    meta = LawMeta(source_pdf=str(pdf_path))

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

    if max_pages is not None:
        total_pages = min(total_pages, max_pages)

    # ── OCR 分批策略：>5 页时每 5 页分批，避免内存溢出 ──
    use_batching = ocr_mode != "off" and total_pages > _OCR_BATCH_SIZE

    if use_batching:
        import gc

        meta_extracted = False

        for batch_start in range(0, total_pages, _OCR_BATCH_SIZE):
            batch_end = min(batch_start + _OCR_BATCH_SIZE, total_pages)
            logger.info(
                "OCR 分批处理: 第 %d-%d 页 / 共 %d 页",
                batch_start + 1, batch_end, total_pages,
            )

            # 每批重新获取引擎（单线程，轻量）
            engine = None
            try:
                from src.ocr import OcrEngine

                # 前一批已 reset，这里会重新初始化
                engine = OcrEngine.get_instance()
            except ImportError:
                pass

            with pdfplumber.open(pdf_path) as pdf:
                for page_idx in range(batch_start, batch_end):
                    page = pdf.pages[page_idx]
                    page_num = page_idx + 1

                    # 安全限制：跳过超大页
                    if page.chars and len(page.chars) > _PAGE_CHAR_LIMIT:
                        logger.warning(
                            "Page %d exceeds char limit (%d), skipping",
                            page_num, len(page.chars),
                        )
                        continue

                    page_lines, ocr_fallback_text = _process_pdf_page(
                        page, page_num, pdf_path, ocr_mode, engine=engine,
                    )

                    for l in page_lines:
                        lines.append(l)

                    if not meta_extracted and page_num == 1:
                        _extract_meta_from_page(
                            page, meta, page_lines,
                            ocr_fallback_text=ocr_fallback_text,
                        )
                        meta_extracted = True

                    # 释放当前页面的缓存数据
                    page.flush_cache()
                    del page_lines
                    if ocr_fallback_text:
                        del ocr_fallback_text

            # 批后释放引擎内存
            try:
                from src.ocr import OcrEngine
                OcrEngine.reset()
            except ImportError:
                pass
            gc.collect()
    else:
        # ── 非 OCR 或 ≤5 页：逐页处理，及时释放页面对象 ──
        import gc

        with pdfplumber.open(pdf_path) as pdf:
            total = min(len(pdf.pages), total_pages)

            for page_idx in range(total):
                page_num = page_idx + 1
                page = pdf.pages[page_idx]

                # 安全限制：跳过超大页
                if page.chars and len(page.chars) > _PAGE_CHAR_LIMIT:
                    logger.warning(
                        "Page %d exceeds char limit (%d), skipping",
                        page_num, len(page.chars),
                    )
                    continue

                page_lines, ocr_fallback_text = _process_pdf_page(
                    page, page_num, pdf_path, ocr_mode,
                )

                for l in page_lines:
                    lines.append(l)

                if page_num == 1:
                    _extract_meta_from_page(
                        page, meta, page_lines,
                        ocr_fallback_text=ocr_fallback_text,
                    )

                # 释放当前页面的缓存数据
                page.flush_cache()
                del page_lines
                if ocr_fallback_text:
                    del ocr_fallback_text

            # 显式释放 pdfplumber 页面缓存
            gc.collect()

    # 排序：先页码，后 y0（从上到下），再 x0（从左到右）
    lines.sort(key=lambda l: (l.page_num, l.y0, l.x0))

    if filter_header_footer:
        lines = _filter_lines(lines)

    return lines, meta


def _extract_page_lines(page, page_num: int) -> list[LineMeta]:
    """从 pdfplumber Page 对象中提取行。

    策略：取 page.extract_words() 再按 y0 聚合成行，
    同时保留每行的 x0/x1 范围。
    """
    from pdfplumber.page import Page

    page_lines: list[LineMeta] = []

    # 方法 A：用 extract_text_lines（pdfplumber >= 0.7）
    if hasattr(page, "extract_text_lines"):
        try:
            raw_lines = page.extract_text_lines(
                strip=True,
                keep_blank_chars=False,
            )
            for rl in raw_lines:
                text = rl.get("text", "").strip()
                if not text:
                    continue
                # 仅提取需要的字体信息，不保留 chars 列表
                chars = rl.get("chars", []) or []
                font_size, bold, fontname = _extract_font_info(chars)
                page_lines.append(LineMeta(
                    text=text,
                    page_num=page_num,
                    x0=rl.get("x0", 0),
                    y0=rl.get("top", 0),
                    x1=rl.get("x1", 0),
                    y1=rl.get("bottom", 0),
                    font_size=font_size,
                    bold=bold,
                    fontname=fontname,
                ))
            del raw_lines
            return page_lines
        except Exception:
            logger.debug("extract_text_lines failed, falling back to word grouping", exc_info=True)

    # 方法 B：用 extract_words 按 y0 聚类合并
    words = page.extract_words(keep_blank_chars=False, x_tolerance=3)
    if not words:
        return page_lines

    # 按 y0 聚类（容差 3pt）
    Y_TOLERANCE = 3
    current_y = words[0]["top"]
    current_x0 = words[0]["x0"]
    current_x1 = words[0]["x1"]
    current_text_parts: list[str] = []
    # 仅收集字体信息，不保留完整 chars 列表
    _font_sizes: list[float] = []
    _fontnames: list[str] = []

    for w in words:
        text = w.get("text", "").strip()
        if not text:
            continue
        if abs(w["top"] - current_y) <= Y_TOLERANCE:
            current_text_parts.append(text)
            current_x0 = min(current_x0, w["x0"])
            current_x1 = max(current_x1, w["x1"])
            if "chars" in w:
                for c in (w["chars"] or []):
                    if c.get("size"):
                        _font_sizes.append(c["size"])
                    if c.get("fontname"):
                        _fontnames.append(c["fontname"])
        else:
            if current_text_parts:
                page_lines.append(_make_line_from_font(
                    line_text="".join(current_text_parts),
                    line_x0=current_x0,
                    line_y0=current_y,
                    line_x1=current_x1,
                    page_num=page_num,
                    font_sizes=_font_sizes,
                    fontnames=_fontnames,
                ))
            current_text_parts = [text]
            current_y = w["top"]
            current_x0 = w["x0"]
            current_x1 = w["x1"]
            _font_sizes = []
            _fontnames = []
            for c in (w.get("chars") or []):
                if c.get("size"):
                    _font_sizes.append(c["size"])
                if c.get("fontname"):
                    _fontnames.append(c["fontname"])

    if current_text_parts:
        page_lines.append(_make_line_from_font(
            line_text="".join(current_text_parts),
            line_x0=current_x0,
            line_y0=current_y,
            line_x1=current_x1,
            page_num=page_num,
            font_sizes=_font_sizes,
            fontnames=_fontnames,
        ))

    del words
    return page_lines


def _extract_page_lines_fitz(
    pdf_path: Path,
    page_num: int,
) -> list[LineMeta]:
    """PyMuPDF 文本提取回退。

    当 pdfplumber 无法提取文字时（如 OCR 后 PDF 的 hOCR 层），
    使用 fitz.get_text(\"blocks\") 获取文字块并转换为 LineMeta。
    """
    try:
        import fitz
    except ImportError:
        logger.debug("PyMuPDF not installed, skipping fitz fallback")
        return []

    page_lines: list[LineMeta] = []
    try:
        doc = fitz.open(str(pdf_path))
        page = doc.load_page(page_num - 1)
        blocks = page.get_text("blocks")
        doc.close()
    except Exception:
        logger.debug("fitz failed to open PDF for page %d", page_num, exc_info=True)
        return []

    for block in blocks:
        # block = (x0, y0, x1, y1, text, block_no, block_type)
        if len(block) < 7:
            continue
        x0, y0, x1, y1, text, _block_no, block_type = block[0], block[1], block[2], block[3], block[4], block[5], block[6]
        if block_type != 0:  # 只取文字块，跳过图片块
            continue
        text = text.strip()
        if not text:
            continue
        page_lines.append(LineMeta(
            text=text,
            page_num=page_num,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            font_size=0,
            bold=False,
            fontname="",
        ))

    # 按 y0 排序
    page_lines.sort(key=lambda l: l.y0)

    if page_lines:
        logger.info(
            "Page %d: PyMuPDF extracted %d lines",
            page_num, len(page_lines),
        )

    return page_lines


def _extract_font_info(chars: list[dict]) -> tuple[float, bool, str]:
    """从 chars 列表提取字体信息，返回 (font_size, bold, fontname)。"""
    font_sizes = [c.get("size", 0) for c in chars if c.get("size")]
    fontnames = [c.get("fontname", "") for c in chars if c.get("fontname")]
    font_size = max(font_sizes) if font_sizes else 0
    bold = "Bold" in " ".join(fontnames) if fontnames else False
    fontname = fontnames[0] if fontnames else ""
    return font_size, bold, fontname


def _make_line_from_font(
    line_text: str,
    line_x0: float,
    line_y0: float,
    line_x1: float,
    page_num: int,
    font_sizes: list[float],
    fontnames: list[str],
) -> LineMeta:
    """从预提取的字体信息构建 LineMeta（不保留 chars 列表）。"""
    font_size = max(font_sizes) if font_sizes else 0
    bold = "Bold" in " ".join(fontnames) if fontnames else False
    fontname = fontnames[0] if fontnames else ""
    return LineMeta(
        text=line_text.strip(),
        page_num=page_num,
        x0=line_x0,
        y0=line_y0,
        x1=line_x1,
        y1=line_y0 + (font_size if font_size else 12),
        font_size=font_size,
        bold=bold,
        fontname=fontname,
    )


def _make_line(
    line_text: str,
    line_x0: float,
    line_y0: float,
    line_x1: float,
    page_num: int,
    chars: list[dict],
) -> LineMeta:
    """从文字列表构建 LineMeta。"""
    font_size, bold, fontname = _extract_font_info(chars)
    return LineMeta(
        text=line_text.strip(),
        page_num=page_num,
        x0=line_x0,
        y0=line_y0,
        x1=line_x1,
        y1=line_y0 + (font_size if font_size else 12),
        font_size=font_size,
        bold=bold,
        fontname=fontname,
    )


def _filter_lines(lines: list[LineMeta]) -> list[LineMeta]:
    filtered: list[LineMeta] = []
    for line in lines:
        if RE_HEADER_FOOTER.match(line.text):
            continue
        filtered.append(line)

    filtered = _remove_cross_page_duplicates(filtered)

    return filtered


def _remove_cross_page_duplicates(lines: list[LineMeta]) -> list[LineMeta]:
    from collections import Counter

    text_page_counts: Counter = Counter()
    for line in lines:
        text_page_counts[(line.text, line.y0)] += 1

    page_set = {line.page_num for line in lines}
    num_pages = len(page_set)

    duplicate_signatures: set[tuple[str, float]] = set()
    for (text, y0), count in text_page_counts.items():
        if count >= max(2, num_pages * 0.5) and len(text) < 80:
            duplicate_signatures.add((text, y0))

    if not duplicate_signatures:
        return lines

    return [line for line in lines if (line.text, line.y0) not in duplicate_signatures]


def _extract_meta_from_page(
    page,
    meta: LawMeta,
    page_lines: list[LineMeta],
    ocr_fallback_text: str = "",
) -> None:
    from src.patterns import RE_DATE, RE_DOC_ID

    # 优先使用已提取的行文本，避免重复调用 page.extract_text()
    text = "\n".join(l.text for l in page_lines)

    # pdfplumber 无文字时使用 OCR 文本回退
    if not text and ocr_fallback_text:
        text = ocr_fallback_text
        logger.debug("对元数据提取使用 OCR 回退文本")

    title_candidates = [l.text for l in page_lines if l.font_size >= 14 and len(l.text) > 4]
    if title_candidates:
        meta.name = title_candidates[0]

    for m in RE_DOC_ID.finditer(text):
        meta.doc_id = m.group(0).strip()
        break

    dates = RE_DATE.findall(text)
    if dates:
        meta.publish_date = dates[0].strip()
        if len(dates) > 1:
            meta.effective_date = dates[1].strip()

    from src.patterns import RE_AUTHORITY
    for m in RE_AUTHORITY.finditer(text):
        meta.issuing_authority = m.group(0).strip()
        break
