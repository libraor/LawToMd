"""页眉页脚过滤模块。

提供标准页眉页脚模式匹配、自定义签名过滤、跨页重复内容移除。
"""

from __future__ import annotations

import logging
from collections import Counter

from src.models import LineMeta
from src.normalizer import get_header_footer_sigs
from src.patterns import RE_HEADER_FOOTER

logger = logging.getLogger(__name__)


def filter_lines(lines: list[LineMeta]) -> list[LineMeta]:
    """过滤页眉页脚行。"""
    filtered: list[LineMeta] = []
    for line in lines:
        # 标准页眉页脚模式
        if RE_HEADER_FOOTER.match(line.text):
            continue
        # 自定义页眉页脚签名
        sigs = get_header_footer_sigs()
        if sigs:
            if any(sig.search(line.text) for sig in sigs):
                continue
        filtered.append(line)

    filtered = remove_cross_page_duplicates(filtered)

    return filtered


def remove_cross_page_duplicates(lines: list[LineMeta]) -> list[LineMeta]:
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
