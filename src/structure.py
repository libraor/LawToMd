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
from typing import Optional

from src.models import DocType, HierarchyNode, Level, LineMeta
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
) -> list[HierarchyNode]:
    """将排好序的 LineMeta 列表解析为 HierarchyNode 树。

    Parameters
    ----------
    lines : list[LineMeta]
        按页码+坐标排序的文本行。
    doc_type : DocType
        文档类型，影响解析策略。

    Returns
    -------
    list[HierarchyNode]
        所有顶层节点，每个节点下挂 children。
    """
    if not lines:
        return []

    # 根据文档类型选择解析策略
    if doc_type == DocType.JUDGMENT:
        raw_nodes = _lines_to_judgment_nodes(lines)
    else:
        raw_nodes = _lines_to_nodes(lines)

    # 构建层级树
    tree = _build_tree(raw_nodes)

    # 提取法律引用标注
    _extract_references(tree)

    return tree


# ── Step 1a: 法规行 → 节点 ────────────────────────────────

# 只有编/章/节/条创建独立的结构节点
_TITLE_LEVELS = frozenset({"part", "chapter", "section", "article"})
_SUB_LEVELS = frozenset({"sub_clause", "item"})


def _lines_to_nodes(lines: list[LineMeta]) -> list[HierarchyNode]:
    """将 LineMeta 行列表转换为扁平 HierarchyNode 列表。

    策略：逐行扫描，遇到新的"标题行"（编/章/节/条）就创建一个新节点，
    非标题行追加到当前节点的 text 中。
    """
    nodes: list[HierarchyNode] = []
    current: Optional[HierarchyNode] = None

    for line in lines:
        text = line.text.strip()
        if not text:
            continue

        level_key = detect_level(text)

        if level_key in _TITLE_LEVELS:
            if current:
                _trim_text(current)
            current = _make_node(level_key, text, line)
            nodes.append(current)
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
        elif current is None:
            # 前导内容（法规标题、颁布信息等），跳过直到遇到第一个结构标题
            continue
        else:
            _append_text(current, text, line)

    if current:
        _trim_text(current)

    return nodes


# ── Step 1b: 判决书行 → 节点 ──────────────────────────────

def _lines_to_judgment_nodes(lines: list[LineMeta]) -> list[HierarchyNode]:
    """将判决书的 LineMeta 行列表转换为扁平 HierarchyNode 列表。

    判决书结构：
    1. 标题（法院名称 + 文书类型）
    2. 当事人信息（原告/被告/第三人）
    3. 诉讼记录（诉称/辩称/审理查明）
    4. 裁判结果（判决如下/裁定如下）
    5. 审判人员署名
    """
    nodes: list[HierarchyNode] = []
    current: Optional[HierarchyNode] = None

    for line in lines:
        text = line.text.strip()
        if not text:
            continue

        level_key = detect_level(text)

        # 当事人信息
        if RE_PARTY.match(text):
            if current:
                _trim_text(current)
            current = HierarchyNode(
                level=Level.PARTY,
                title=text,
                text="",
                page_num=line.page_num,
            )
            nodes.append(current)
        # 诉讼记录段落
        elif RE_PROCEDURE_HEADER.match(text):
            if current:
                _trim_text(current)
            current = HierarchyNode(
                level=Level.PROCEDURE,
                title=text,
                text="",
                page_num=line.page_num,
            )
            nodes.append(current)
        # 裁判结果段落
        elif RE_RULING_HEADER.match(text):
            if current:
                _trim_text(current)
            current = HierarchyNode(
                level=Level.RULING,
                title=text,
                text="",
                page_num=line.page_num,
            )
            nodes.append(current)
        # 审判人员署名
        elif RE_JUDGES.match(text):
            if current:
                _trim_text(current)
            current = HierarchyNode(
                level=Level.JUDGES,
                title=text,
                text="",
                page_num=line.page_num,
            )
            nodes.append(current)
        # 法条结构（判决书中也可能引用法条）
        elif level_key in _TITLE_LEVELS:
            if current:
                _trim_text(current)
            current = _make_node(level_key, text, line)
            nodes.append(current)
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
        elif current is not None:
            _append_text(current, text, line)

    if current:
        _trim_text(current)

    return nodes


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


def _append_text(node: HierarchyNode, text: str, line: LineMeta) -> None:
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

def _build_tree(nodes: list[HierarchyNode]) -> list[HierarchyNode]:
    root: list[HierarchyNode] = []
    stack: list[HierarchyNode] = []

    for node in nodes:
        while stack and _level_order(stack[-1].level) >= _level_order(node.level):
            stack.pop()

        if stack:
            parent = stack[-1]
            siblings = parent.children
            if siblings and siblings[-1].title == node.title and not _has_content(siblings[-1]):
                siblings[-1] = node
            else:
                siblings.append(node)
            node.parent = parent
            node.hierarchy_path = parent.hierarchy_path + [node.title]
        else:
            if root and root[-1].title == node.title and not _has_content(root[-1]):
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


LEVEL_ORDER = {
    Level.PART: 1,
    Level.CHAPTER: 2,
    Level.SECTION: 3,
    Level.ARTICLE: 4,
    Level.CLAUSE: 5,
    Level.SUB_CLAUSE: 6,
    Level.ITEM: 7,
    # 判决书层级（与法规同级并列）
    Level.PARTY: 3,
    Level.PROCEDURE: 3,
    Level.RULING: 3,
    Level.JUDGES: 4,
}


def _level_order(level: Level) -> int:
    """返回层级的排序值（越小越上层）。"""
    return LEVEL_ORDER.get(level, 99)


# ── 法律引用标注提取 ──────────────────────────────────────

def _extract_references(tree: list[HierarchyNode]) -> None:
    """递归遍历树，提取每个节点中的法律引用标注。"""
    for node in tree:
        full = node.full_text()
        if "《" in full:
            refs = RE_LAW_REFERENCE.findall(full)
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
