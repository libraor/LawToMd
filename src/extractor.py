"""PDF 文本提取层。

封装 pdfplumber，提取文本的同时保留排版信息（坐标、字号、是否加粗），
用于后续的层级推断和结构识别。

优化特性：
- 文本规范化（全角/半角统一、OCR 常见错误修正）
- 文档类型自动检测（法律法规/判决书/司法解释）
- 法律引用标注提取
- 页眉页脚增强过滤

用法:
    lines = extract_pdf("民法典.pdf")
    for line in lines:
        print(line.text, line.page_num, line.font_size)
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from pathlib import Path
from typing import Literal, Optional

from src.models import DocType, LawMeta, LineMeta
from src.patterns import (
    RE_AUTHORITY,
    RE_CASE_NUMBER,
    RE_DATE,
    RE_DOC_ID,
    RE_HEADER_FOOTER,
    RE_JUDGMENT_TITLE,
    detect_doc_type,
)

_OcrMode = Literal["auto", "force", "off"]
_OcrEngine = Literal["auto", "paddle", "lite"]

logger = logging.getLogger(__name__)

# pdfplumber 单页字符数硬限制，超出自动跳过
_PAGE_CHAR_LIMIT = 200_000
_OCR_BATCH_SIZE = 5

# ── 文本规范化规则 ────────────────────────────────────────

# 全角→半角映射（仅实际需要转换的字符；中文标点保留全角）
_FULLWIDTH_MAP = str.maketrans({
    "　": " ",    # 全角空格→半角
    "─": "-",     # 长破折号
    "—": "-",     # 破折号
})

# OCR 常见误识别修正
_OCR_FIXES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"l令"), "令"),
    (re.compile(r"第0条"), "第十条"),   # 0 通常是"十"的误识别
    (re.compile(r"第O条"), "第〇条"),   # O 通常是"〇"的误识别
    (re.compile(r"第I条"), "第一条"),   # I 通常是"一"的误识别
    (re.compile(r"第l条"), "第一条"),   # l 通常是"一"的误识别
]

# ── 替换配置加载 ──────────────────────────────────────────

_replacements: list[tuple[re.Pattern, str]] | None = None
_header_footer_sigs: list[re.Pattern] | None = None


def _load_replace_config() -> None:
    """加载 config/replace.yaml 中的替换规则（仅首次调用时加载）。"""
    global _replacements, _header_footer_sigs

    if _replacements is not None:
        return

    config_path = Path(__file__).resolve().parent.parent / "config" / "replace.yaml"
    _replacements = []
    _header_footer_sigs = []

    if not config_path.exists():
        return

    try:
        import yaml

        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        for item in cfg.get("replacements", []):
            if isinstance(item, (list, tuple)) and len(item) == 2:
                _replacements.append((re.compile(re.escape(item[0])), item[1]))

        for sig in cfg.get("header_footer_signatures", []):
            _header_footer_sigs.append(re.compile(re.escape(sig)))

        logger.debug("加载替换规则: %d 条, 页眉页脚签名: %d 条",
                     len(_replacements), len(_header_footer_sigs))
    except Exception as e:
        logger.warning("加载 replace.yaml 失败: %s", e)


def normalize_text(text: str) -> str:
    """对提取的文本进行规范化处理。

    处理内容：
    - 全角空格→半角空格
    - OCR 常见误识别修正
    - 自定义替换规则（config/replace.yaml）

    注意：法律文本中的中文标点（，。：；等）保留全角，不做转换。
    """
    # 全角字符规范化（空格、破折号等）
    text = text.translate(_FULLWIDTH_MAP)

    # OCR 误识别修正
    for pat, repl in _OCR_FIXES:
        text = pat.sub(repl, text)

    # 自定义替换规则
    _load_replace_config()
    if _replacements:
        for pat, repl in _replacements:
            text = pat.sub(repl, text)

    # 多余空白压缩
    text = re.sub(r" {2,}", " ", text)

    return text.strip()


def _process_pdf_page(
    page,
    page_num: int,
    pdf_path: Path,
    ocr_mode: _OcrMode,
    ocr_engine: _OcrEngine = "auto",
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

                engine = OcrEngine.get_instance(backend=ocr_engine)

            image, effective_dpi = pdf_page_to_image(pdf_path, page_num - 1, dpi=300)
            page_lines = engine.ocr_page(image, page_num=page_num, dpi=effective_dpi)
            ocr_fallback_text = "\n".join(line.text for line in page_lines)
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

    # 对提取的文本进行规范化
    for line in page_lines:
        line.text = normalize_text(line.text)

    return page_lines, ocr_fallback_text


def extract_pdf(
    pdf_path: str | Path,
    *,
    max_pages: Optional[int] = None,
    filter_header_footer: bool = True,
    ocr_mode: _OcrMode = "off",
    ocr_engine: _OcrEngine = "auto",
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
    ocr_engine : "auto" | "paddle" | "lite"
        OCR 引擎选择（默认 "auto"）：
        - "auto"   → 根据设备性能自动推荐
        - "paddle" → PaddleOCR 高性能后端
        - "lite"   → RapidOCR 轻量版后端

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
            ocr_available = False
            try:
                from src.ocr import OcrEngine

                # 前一批已 reset，这里会重新初始化
                engine = OcrEngine.get_instance(backend=ocr_engine)
                ocr_available = True
            except ImportError:
                logger.warning("OCR 依赖未安装，所有页面使用 pdfplumber 提取")

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

                    effective_ocr_mode = ocr_mode if ocr_available else "off"
                    page_lines, ocr_fallback_text = _process_pdf_page(
                        page, page_num, pdf_path, effective_ocr_mode, ocr_engine=ocr_engine, engine=engine,
                    )

                    for line in page_lines:
                        lines.append(line)

                    if not meta_extracted and page_num == 1:
                        _extract_meta_from_page(
                            meta, page_lines,
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
                    page, page_num, pdf_path, ocr_mode, ocr_engine=ocr_engine,
                )

                for line in page_lines:
                    lines.append(line)

                if page_num == 1:
                    _extract_meta_from_page(
                        meta, page_lines,
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
    lines.sort(key=lambda line: (line.page_num, line.y0, line.x0))

    if filter_header_footer:
        lines = _filter_lines(lines)

    return lines, meta


def _extract_page_lines(page, page_num: int) -> list[LineMeta]:
    """从 pdfplumber Page 对象中提取行。

    策略：取 page.extract_words() 再按 y0 聚合成行，
    同时保留每行的 x0/x1 范围。
    """
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


def _filter_lines(lines: list[LineMeta]) -> list[LineMeta]:
    """过滤页眉页脚行。"""
    _load_replace_config()

    filtered: list[LineMeta] = []
    for line in lines:
        # 标准页眉页脚模式
        if RE_HEADER_FOOTER.match(line.text):
            continue
        # 自定义页眉页脚签名
        if _header_footer_sigs:
            if any(sig.search(line.text) for sig in _header_footer_sigs):
                continue
        filtered.append(line)

    filtered = _remove_cross_page_duplicates(filtered)

    return filtered


def _remove_cross_page_duplicates(lines: list[LineMeta]) -> list[LineMeta]:
    """移除跨页重复内容（页眉页脚）。"""
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

    # ── 标题提取 ──
    title_candidates = [line.text for line in page_lines if line.font_size >= 14 and len(line.text) > 4]
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
