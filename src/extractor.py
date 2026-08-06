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
from pathlib import Path
from typing import Optional

from src.header_footer import filter_lines as _filter_lines
from src.metadata import extract_meta_from_page as _extract_meta_from_page
from src.models import LawMeta, LineMeta
from src.normalizer import normalize_text
from src.types import OcrMode

logger = logging.getLogger(__name__)

# pdfplumber 单页字符数硬限制，超出自动跳过
_PAGE_CHAR_LIMIT = 200_000
_OCR_BATCH_SIZE = 5

# ── 双栏页面识别与重建 ──────────────────────────────────
# 法律检索手册等文档常采用双栏排版（左栏条文、右栏规范标注）。
# 双栏页按阅读顺序重建：先左栏整列 → 中栏标题 → 右栏整列。
_TWO_COL_GAP_RATIO = 0.05   # 栏间间隙判定：大于页宽此比例视为栏间隙
_TWO_COL_NARROW = 0.45      # 窄行判定：行宽小于页宽此比例
_TWO_COL_MULTI_RATIO = 0.6  # 宽行中横跨双栏（含栏间隙）的最低比例


def _process_pdf_page(
    page,
    page_num: int,
    pdf_path: Path,
    ocr_mode: OcrMode,
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

    # 非 OCR 路径：提取表格行
    if not use_ocr:
        table_lines = _extract_table_lines(page, page_num)
        page_lines.extend(table_lines)

    return page_lines, ocr_fallback_text


def extract_pdf(
    pdf_path: str | Path,
    *,
    max_pages: Optional[int] = None,
    filter_header_footer: bool = True,
    ocr_mode: OcrMode = "off",
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

    # ── 判断是否需要 OCR 分批 ──
    # 仅 OCR 模式下需要提前获取总页数来决定分批策略
    use_batching = False
    total_pages = 0

    if ocr_mode != "off":
        with pdfplumber.open(pdf_path) as pdf:
            raw_total_pages = len(pdf.pages)
        total_pages = min(raw_total_pages, max_pages) if max_pages else raw_total_pages
        use_batching = total_pages > _OCR_BATCH_SIZE

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
                engine = OcrEngine.get_instance()
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
                        page, page_num, pdf_path, effective_ocr_mode, engine=engine,
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
        # ── 非 OCR 或 ≤5 页：单次打开，逐页处理 ──
        import gc

        with pdfplumber.open(pdf_path) as pdf:
            raw_pages = len(pdf.pages)
            total = min(raw_pages, max_pages) if max_pages else raw_pages

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


def _rebuild_two_column_lines(
    raw_lines: list[dict], page, page_num: int
) -> Optional[list[LineMeta]]:
    """若页面为双栏排版，重建为阅读顺序（左栏→中栏→右栏）。

    双栏判定依据：
    1. 存在足够多的窄行（行宽 < 45% 页宽），且左右两侧各有窄行；
    2. 宽行（≥45% 页宽）中可被栏间间隙拆分为多段的比例 ≥ 60%。

    重建时宽行按字符 x 间隙拆段，丢弃孤立页码段，段落按
    其中点 x 归入左/右栏；窄行按整体中点归入左/右/中栏。

    返回 None 表示非双栏页。
    """
    rows = [rl for rl in raw_lines if (rl.get("text") or "").strip()]
    if len(rows) < 10:
        return None
    width = float(page.width)
    if not width:
        return None

    # 宽行：横跨页面左右两侧的长行
    wide = [r for r in rows if (r["x1"] - r["x0"]) >= width * _TWO_COL_NARROW]
    if not wide:
        return None

    # 双栏判定：宽行中存在"栏间大间隙"（≥5% 页宽）的比例
    # 单栏正文的宽行内只有词间距（<5% 页宽），不会被误判；
    # 双栏页的宽行横跨左右栏，栏间隙显著大于词间距。
    big_gap = width * _TWO_COL_GAP_RATIO
    big_n = sum(1 for r in wide if _max_char_gap(r.get("chars") or []) >= big_gap)
    if big_n / len(wide) < _TWO_COL_MULTI_RATIO:
        return None

    # 拆段聚簇：窄行整行为一段，宽行按大间隙拆段
    segs: list[tuple[float, float, float]] = []
    for rl in rows:
        span = rl["x1"] - rl["x0"]
        if span < width * _TWO_COL_NARROW:
            segs.append(((rl["x0"] + rl["x1"]) / 2, rl["x0"], rl["x1"]))
        else:
            for seg_text, seg_x0, seg_x1 in _split_chars_by_big_gap(
                rl.get("chars") or [], big_gap
            ):
                if not seg_text:
                    continue
                segs.append(((seg_x0 + seg_x1) / 2, seg_x0, seg_x1))
    if len(segs) < 20:
        return None

    # k-means(k=2) 求分栏线：两簇中心距足够远且两侧段数均衡
    centers = [s[0] for s in segs]
    split, m1, m2 = _kmeans_split(centers)
    if split is None:
        return None
    left_segs = [s for s in segs if s[0] < split]
    right_segs = [s for s in segs if s[0] >= split]
    if len(left_segs) < 6 or len(right_segs) < 6:
        return None
    if (m2 - m1) < width * 0.15:
        return None

    left_lines: list[LineMeta] = []
    center_lines: list[LineMeta] = []
    right_lines: list[LineMeta] = []

    for rl in rows:
        text = rl.get("text", "").strip()
        x0, x1, top = rl["x0"], rl["x1"], rl["top"]
        bottom = rl.get("bottom", top + 10)
        chars = rl.get("chars") or []
        font_size, bold, fontname = _extract_font_info(chars)

        if (x1 - x0) < width * _TWO_COL_NARROW:
            # 窄行：单栏内容或通栏标题
            mid = (x0 + x1) / 2
            if x0 < split < x1:
                target = center_lines
            elif mid < split:
                target = left_lines
            else:
                target = right_lines
            target.append(LineMeta(
                text=text, page_num=page_num,
                x0=x0, y0=top, x1=x1, y1=bottom,
                font_size=font_size, bold=bold, fontname=fontname,
            ))
        else:
            # 宽行：按大间隙拆段，左右栏各归各
            segs = _split_chars_by_big_gap(chars, width * _TWO_COL_GAP_RATIO)
            if segs and segs[0][1] < split < segs[0][2]:
                # 文本横跨分栏线：若行内出现两个条文号，则按第二个条文号切分
                # （OCR 文本层可能把左右栏字符挤在一起，无足够间隙）
                article_segs = _split_by_second_article(chars, split)
                if len(article_segs) >= 2:
                    segs = article_segs
            for seg_text, seg_x0, seg_x1 in segs:
                if not seg_text:
                    continue
                # 丢弃孤立页码段（纯数字且很短）
                if seg_text.isdigit() and len(seg_text) <= 3:
                    continue
                seg_mid = (seg_x0 + seg_x1) / 2
                target = right_lines if seg_mid >= split else left_lines
                target.append(LineMeta(
                    text=seg_text, page_num=page_num,
                    x0=seg_x0, y0=top, x1=seg_x1, y1=bottom,
                    font_size=font_size, bold=bold, fontname=fontname,
                ))

    # 各栏内部按 y 排序；最终顺序：左栏 → 中栏 → 右栏
    left_lines.sort(key=lambda l: l.y0)
    center_lines.sort(key=lambda l: l.y0)
    right_lines.sort(key=lambda l: l.y0)
    result = left_lines + center_lines + right_lines

    # 调整 y0 使 extract_pdf 的全局排序保持栏顺序：
    # 中栏行偏移一页高、右栏行偏移两页高（相对左栏），
    # 保证同页内 左栏 < 中栏 < 右栏 完全分离。
    height = float(page.height) or float(page.bbox[3] - page.bbox[1]) or width
    for line in center_lines:
        line.y0 += height
        line.y1 += height
    for line in right_lines:
        line.y0 += height * 2
        line.y1 += height * 2
    return result


def _kmeans_split(
    centers: list[float], iters: int = 50
) -> tuple[Optional[float], float, float]:
    """k-means(k=2) 聚类，返回 (split, m1, m2)，无法聚类时 split=None。"""
    if not centers:
        return None, 0.0, 0.0
    lo, hi = min(centers), max(centers)
    if hi - lo < 1e-6:
        return None, 0.0, 0.0
    m1, m2 = lo + (hi - lo) * 0.3, lo + (hi - lo) * 0.7
    for _ in range(iters):
        g1 = [c for c in centers if abs(c - m1) <= abs(c - m2)]
        g2 = [c for c in centers if abs(c - m1) > abs(c - m2)]
        if not g1 or not g2:
            break
        n1, n2 = sum(g1) / len(g1), sum(g2) / len(g2)
        if abs(n1 - m1) < 1e-6 and abs(n2 - m2) < 1e-6:
            m1, m2 = n1, n2
            break
        m1, m2 = n1, n2
    return (m1 + m2) / 2, m1, m2


def _split_by_second_article(
    chars: list[dict], split: float
) -> list[tuple[str, float, float]]:
    """将一行字符按"第二个条文号"切分为两段。

    适用于 OCR 文本层把左右栏字符挤在一起、无足够间隙的情况：
    此时若行内出现两个"第X条"，则在第二个条文号前切分。
    若找不到两个条文号，则按 split 切分。
    """
    import re

    if not chars:
        return []
    sorted_chars = sorted(chars, key=lambda c: c.get("x0", 0))
    full = "".join(c.get("text", "") for c in sorted_chars)
    # 找所有条文号在全文中的字符位置
    positions: list[int] = []
    for m in re.finditer(r"第\s*\d+\s*条", full):
        positions.append(m.start())
    if len(positions) >= 2:
        cut = positions[1]
        # 仅当第二个条文号起始位于分栏线右侧时才切分，
        # 避免误切同一栏内"第X条、第Y条"的并列引用。
        if cut < len(sorted_chars) and (sorted_chars[cut].get("x0", 0)) >= split:
            left = sorted_chars[:cut]
            right = sorted_chars[cut:]
            out: list[tuple[str, float, float]] = []
            for group in (left, right):
                if not group:
                    continue
                text = "".join(c.get("text", "") for c in group).strip()
                if not text:
                    continue
                x0 = min(c.get("x0", 0) for c in group)
                x1 = max(c.get("x1", 0) for c in group)
                out.append((text, x0, x1))
            return out
    return _split_chars_at_split(sorted_chars, split)


def _split_chars_at_split(
    chars: list[dict], split: float
) -> list[tuple[str, float, float]]:
    """将一行字符按分栏线切分为左右两段，返回 (text, x0, x1)。"""
    if not chars:
        return []
    left_chars = [c for c in chars if (c.get("x0", 0) + c.get("x1", 0)) / 2 < split]
    right_chars = [c for c in chars if (c.get("x0", 0) + c.get("x1", 0)) / 2 >= split]
    out: list[tuple[str, float, float]] = []
    for group in (left_chars, right_chars):
        if not group:
            continue
        text = "".join(c.get("text", "") for c in group).strip()
        if not text:
            continue
        x0 = min(c.get("x0", 0) for c in group)
        x1 = max(c.get("x1", 0) for c in group)
        out.append((text, x0, x1))
    return out


def _max_char_gap(chars: list[dict]) -> float:
    """一行字符中相邻字符的最大 x 间隙（pt）。"""
    if not chars:
        return 0.0
    sorted_chars = sorted(chars, key=lambda c: c.get("x0", 0))
    mx = 0.0
    prev_x1 = sorted_chars[0].get("x1", 0)
    for c in sorted_chars[1:]:
        g = c.get("x0", 0) - prev_x1
        if g > mx:
            mx = g
        prev_x1 = c.get("x1", 0)
    return mx


def _split_chars_by_big_gap(
    chars: list[dict], big_gap: float
) -> list[tuple[str, float, float]]:
    """将一行字符按栏间大间隙拆分为多段，返回 (text, x0, x1)。

    仅在大间隙（栏间隙）处切分，词间距不会被误拆。
    """
    if not chars:
        return []
    sorted_chars = sorted(chars, key=lambda c: c.get("x0", 0))
    segments: list[list[dict]] = []
    cur = [sorted_chars[0]]
    for c in sorted_chars[1:]:
        if c.get("x0", 0) - cur[-1].get("x1", 0) > big_gap:
            segments.append(cur)
            cur = [c]
        else:
            cur.append(c)
    segments.append(cur)

    out: list[tuple[str, float, float]] = []
    for seg in segments:
        text = "".join(c.get("text", "") for c in seg).strip()
        if not text:
            continue
        x0 = min(c.get("x0", 0) for c in seg)
        x1 = max(c.get("x1", 0) for c in seg)
        out.append((text, x0, x1))
    return out


def _extract_page_lines(page, page_num: int) -> list[LineMeta]:
    """从 pdfplumber Page 对象中提取行。

    策略：优先提取文本行；若页面为双栏排版，按阅读顺序重建
    （左栏 → 中栏标题 → 右栏），否则按原顺序返回。
    """
    page_lines: list[LineMeta] = []

    # 方法 A：用 extract_text_lines（pdfplumber >= 0.7）
    if hasattr(page, "extract_text_lines"):
        try:
            raw_lines = page.extract_text_lines(
                strip=True,
                keep_blank_chars=False,
            )
            # 双栏页面按阅读顺序重建
            rebuilt = _rebuild_two_column_lines(raw_lines, page, page_num)
            if rebuilt is not None:
                return rebuilt
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


def _extract_table_lines(page, page_num: int) -> list[LineMeta]:
    """从 pdfplumber Page 中提取表格，转为 Markdown 表格行。"""
    table_lines: list[LineMeta] = []
    try:
        tables = page.extract_tables()
    except Exception:
        return table_lines

    for table in tables or []:
        if not table or len(table) < 2:
            continue
        # 将表格转为 Markdown 格式
        rows: list[str] = []
        for i, row in enumerate(table):
            cells = [str(cell or "").strip().replace("\n", " ") for cell in row]
            rows.append("| " + " | ".join(cells) + " |")
            # 首行后添加分隔行
            if i == 0:
                sep = "| " + " | ".join("---" for _ in cells) + " |"
                rows.append(sep)

        # 合并为单个 LineMeta，标记为表格
        table_text = "\n".join(rows)
        # 用表格的 bbox 估算坐标
        table_lines.append(LineMeta(
            text=table_text,
            page_num=page_num,
            x0=0,
            y0=0,
            x1=0,
            y1=0,
            is_table=True,
        ))

    return table_lines


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
