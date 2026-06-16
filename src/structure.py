"""法律结构识别引擎。

从 LineMeta 列表出发，遍历各行，通过正则 + 排版启发式判定层级，
构建树状的 HierarchyNode 结构。

支持文档类型：
- 法律法规：编/章/节/条/款/项/目
- 判决书：当事人/诉讼记录/裁判结果/审判人员
- 司法解释：按法规结构解析

核心流程:
    lines → detect_level() → assign_parent() → build_path() → nodes
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Optional

from src.models import DocType, HierarchyNode, LawMeta, Level, LineMeta
from src.patterns import (
    RE_JUDGES,
    RE_LAW_REFERENCE,
    RE_PARTY,
    RE_PROCEDURE_HEADER,
    RE_RULING_HEADER,
    detect_level,
    parse_article_number,
)

logger = logging.getLogger(__name__)


def parse_structure(
    lines: list[LineMeta],
    doc_type: DocType = DocType.UNKNOWN,
    meta: Optional[LawMeta] = None,
) -> list[HierarchyNode]:
    """将排好序的 LineMeta 列表解析为 HierarchyNode 树。

    Parameters
    ----------
    lines : list[LineMeta]
        按页码+坐标排序的文本行。
    doc_type : DocType
        文档类型，影响解析策略。
    meta : LawMeta, optional
        法规元数据，用于保存前导内容（preamble）。

    Returns
    -------
    list[HierarchyNode]
        所有顶层节点，每个节点下挂 children。
    """
    if not lines:
        return []

    # 根据文档类型选择解析策略
    raw_nodes = _lines_to_nodes(lines, doc_type=doc_type, meta=meta)

    # 构建层级树
    tree = _build_tree(raw_nodes)

    # 提取法律引用标注
    _extract_references(tree)

    return tree


# ── Step 1: 行 → 节点（统一策略） ──────────────────────────

# 只有编/章/节/条创建独立的结构节点
_TITLE_LEVELS = frozenset({"part", "chapter", "section", "article"})
_SUB_LEVELS = frozenset({"sub_clause", "item"})

# 款（CLAUSE）缩进检测阈值：x0 差值超过此值视为缩进（即新款）
_CLAUSE_INDENT_THRESHOLD = 10.0  # pt

# 判决书专用正则 → Level 映射（lru_cache 保证线程安全且只初始化一次）


@lru_cache(maxsize=1)
def _get_judgment_patterns() -> tuple[list[tuple[re.Pattern, Level]], ...]:
    """获取判决书正则映射（缓存，线程安全）。"""
    return ([
        (RE_PARTY, Level.PARTY),
        (RE_PROCEDURE_HEADER, Level.PROCEDURE),
        (RE_RULING_HEADER, Level.RULING),
        (RE_JUDGES, Level.JUDGES),
    ],)


def _lines_to_nodes(
    lines: list[LineMeta],
    doc_type: DocType = DocType.UNKNOWN,
    meta: Optional[LawMeta] = None,
) -> list[HierarchyNode]:
    """将 LineMeta 行列表转换为扁平 HierarchyNode 列表。

    统一处理法规和判决书，通过 doc_type 选择标题行判定策略：
    - 法规：编/章/节/条/款/项/目
    - 判决书：当事人/诉讼记录/裁判结果/审判人员 + 法条结构
    """
    is_judgment = doc_type == DocType.JUDGMENT
    judgment_patterns = _get_judgment_patterns()[0] if is_judgment else []

    nodes: list[HierarchyNode] = []
    current: Optional[HierarchyNode] = None
    # 记录当前条标题的 x0，用于款（CLAUSE）缩进检测
    article_x0: Optional[float] = None
    # 收集前导内容（第一个结构标题之前的文本）
    preamble_parts: list[str] = []

    for line in lines:
        text = line.text.strip()
        if not text:
            continue

        level_key = detect_level(text)

        # 判决书专用标题判定（优先于法条结构）
        if is_judgment:
            matched_judgment = False
            for pat, lvl in judgment_patterns:
                if pat.match(text):
                    if current:
                        _trim_text(current)
                    current = HierarchyNode(
                        level=lvl,
                        title=text,
                        text="",
                        page_num=line.page_num,
                    )
                    nodes.append(current)
                    article_x0 = None
                    matched_judgment = True
                    break
            if matched_judgment:
                continue

        # 法条结构标题判定
        if level_key in _TITLE_LEVELS:
            if current:
                _trim_text(current)
            current = _make_node(level_key, text, line)
            nodes.append(current)
            # 记录条标题的 x0，用于后续款缩进检测
            if level_key == "article":
                article_x0 = line.x0
            else:
                article_x0 = None
        elif level_key in _SUB_LEVELS:
            if current is None:
                current = _make_orphan_node(line)
                nodes.append(current)
            sub_node = HierarchyNode(
                level=Level.SUB_CLAUSE if level_key == "sub_clause" else Level.ITEM,
                title=text,
                text=text,
                page_num=line.page_num,
                parent=current,
                hierarchy_path=current.hierarchy_path + [text],
            )
            current.children.append(sub_node)
            article_x0 = None
        elif current is None:
            # 前导内容（法规标题、颁布信息等），收集到 preamble
            preamble_parts.append(text)
            continue
        elif _is_clause_indent(line, current, article_x0):
            # 款（CLAUSE）：条下缩进的段落
            clause_node = HierarchyNode(
                level=Level.CLAUSE,
                title="",
                text=text,
                page_num=line.page_num,
                parent=current,
                hierarchy_path=current.hierarchy_path + ["款"],
            )
            current.children.append(clause_node)
        elif line.is_table:
            # 表格行直接追加到当前节点（保持 Markdown 表格格式）
            _append_text(current, text, line)
        else:
            _append_text(current, text, line)

    if current:
        _trim_text(current)

    # 将前导内容保存到 meta
    if preamble_parts and meta is not None:
        meta.extra["preamble"] = "\n".join(preamble_parts)

    return nodes


def _is_clause_indent(
    line: LineMeta,
    current: HierarchyNode,
    article_x0: Optional[float],
) -> bool:
    """判断一行是否为款（CLAUSE）——条下缩进的段落。

    条件：
    1. 当前节点是 ARTICLE 级别
    2. 已有条标题的 x0 基准
    3. 当前行 x0 明显大于条标题 x0（缩进超过阈值）
    4. 当前条节点已有正文（即不是条标题后的第一行，第一行通常紧跟条标题）
    """
    if current.level != Level.ARTICLE:
        return False
    if article_x0 is None:
        return False
    indent = line.x0 - article_x0
    if indent < _CLAUSE_INDENT_THRESHOLD:
        return False
    # 条下第一行正文通常紧跟条标题（缩进也较大），不算新款
    # 只有当条已有正文内容时，后续缩进行才算新款
    if not current.text:
        return False
    return True


# ── 节点构建辅助 ──────────────────────────────────────────

def _make_node(level_key: str, text: str, line: LineMeta) -> HierarchyNode:
    try:
        level = Level(level_key)
    except ValueError:
        level = Level.ARTICLE
    number = parse_article_number(text) if level == Level.ARTICLE else ""
    return HierarchyNode(
        level=level,
        number=number,
        title=text,
        text="",
        page_num=line.page_num,
    )


def _make_orphan_node(line: LineMeta) -> HierarchyNode:
    return HierarchyNode(
        level=Level.ARTICLE,
        number="",
        title="",
        text="",
        page_num=line.page_num,
    )


def _append_text(node: HierarchyNode, text: str, _line: LineMeta | None = None) -> None:
    """向节点追加正文，处理换行。"""
    if node.text:
        node.text += "\n" + text
    else:
        node.text = text


def _trim_text(node: HierarchyNode) -> None:
    """清理节点末尾空白和多余的换行。"""
    node.text = node.text.strip()
    node.title = node.title.strip()


# ── Step 2: 扁平节点 → 树 ──────────────────────────────

def _is_duplicate_node(existing: HierarchyNode, incoming: HierarchyNode) -> bool:
    """判断 incoming 是否为 existing 的目录重复（同名同层级且前者无内容）。"""
    return (
        existing.title == incoming.title
        and existing.level == incoming.level
        and not _has_content(existing)
    )


def _build_tree(nodes: list[HierarchyNode]) -> list[HierarchyNode]:
    root: list[HierarchyNode] = []
    stack: list[HierarchyNode] = []

    for node in nodes:
        while stack and stack[-1].level.sort_order() >= node.level.sort_order():
            stack.pop()

        if stack:
            parent = stack[-1]
            siblings = parent.children
            if siblings and _is_duplicate_node(siblings[-1], node):
                siblings[-1] = node
            else:
                siblings.append(node)
            node.parent = parent
            node.hierarchy_path = parent.hierarchy_path + [node.title]
        else:
            if root and _is_duplicate_node(root[-1], node):
                root[-1] = node
            else:
                root.append(node)
            node.hierarchy_path = [node.title]

        stack.append(node)

    return root


def _has_content(node: HierarchyNode) -> bool:
    """检查节点是否有实质内容（正文或嵌套条目）。"""
    if node.text:
        return True
    for child in node.children:
        if child.text or child.children:
            return True
    return False


# ── 法律引用标注提取 ──────────────────────────────────────

def _extract_references(tree: list[HierarchyNode]) -> None:
    """递归遍历树，提取每个节点中的法律引用标注。"""
    for node in tree:
        full = node.full_text()
        if "《" in full:
            refs = [m.group(0) for m in RE_LAW_REFERENCE.finditer(full)]
            if refs:
                node.law_references = refs
        _extract_references(node.children)


# ── 遍历辅助 ──────────────────────────────────────────────

def flatten_leaves(node: HierarchyNode) -> list[HierarchyNode]:
    """深度遍历，返回所有叶子节点（无 children 的节点）。

    通常叶子节点就是 Article + Clause 组合。
    """
    if not node.children:
        return [node]
    leaves = []
    for child in node.children:
        leaves.extend(flatten_leaves(child))
    return leaves
