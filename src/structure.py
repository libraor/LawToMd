"""法律结构识别引擎。

从 LineMeta 列表出发，遍历各行，通过正则 + 排版启发式判定层级，
构建树状的 HierarchyNode 结构。

核心流程:
    lines → detect_level() → assign_parent() → build_path() → nodes
"""

from __future__ import annotations

import logging
from typing import Optional

from src.models import HierarchyNode, Level, LineMeta
from src.patterns import detect_level, parse_article_number

logger = logging.getLogger(__name__)


def parse_structure(lines: list[LineMeta]) -> list[HierarchyNode]:
    """将排好序的 LineMeta 列表解析为 HierarchyNode 树。

    返回值是所有顶层节点（通常是 PART 或 CHAPTER 或 ARTICLE），
    每个节点下挂 children。
    """
    if not lines:
        return []

    # 第一步：每行做层级判定，合并连续的同级内容
    raw_nodes = _lines_to_nodes(lines)

    # 第二步：构建层级树
    tree = _build_tree(raw_nodes)

    return tree


# ── Step 1: 行 → 节点 ─────────────────────────────────────

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
}


def _level_order(level: Level) -> int:
    """返回层级的排序值（越小越上层）。"""
    return LEVEL_ORDER.get(level, 99)


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

