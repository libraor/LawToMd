"""Markdown 组装层。

将 HierarchyNode 树转换为完整的 Markdown 文档。
"""

from __future__ import annotations

from src.models import HierarchyNode, LawMeta, Level


def build_markdown(
    tree: list[HierarchyNode],
    meta: LawMeta,
    *,
    include_toc: bool = False,
    article_anchor: bool = True,
) -> str:
    """将层级树渲染为完整的 Markdown 字符串。

    Parameters
    ----------
    tree : list[HierarchyNode]
        结构识别后的树节点。
    meta : LawMeta
        法规元数据，放在文档头部。
    include_toc : bool
        是否在开头生成目录（默认 False）。
    article_anchor : bool
        是否在每条后添加 HTML anchor 注释（默认 True）。

    Returns
    -------
    str
        完整的 Markdown 文档。
    """
    parts: list[str] = []

    # 元数据头
    _write_metadata_header(parts, meta)

    # 目录（可选）
    if include_toc:
        _write_toc(parts, tree)

    # 正文
    for node in tree:
        _render_node(parts, node, article_anchor=article_anchor)

    return "\n".join(parts)


def _write_metadata_header(parts: list[str], meta: LawMeta) -> None:
    """写入 YAML-like 元数据头。"""
    parts.append("---")
    if meta.name:
        parts.append(f"title: {meta.name}")
    if meta.doc_id:
        parts.append(f"doc_id: {meta.doc_id}")
    if meta.publish_date:
        parts.append(f"publish_date: {meta.publish_date}")
    if meta.effective_date:
        parts.append(f"effective_date: {meta.effective_date}")
    if meta.issuing_authority:
        parts.append(f"authority: {meta.issuing_authority}")
    if meta.source_pdf:
        parts.append(f"source: {meta.source_pdf}")
    parts.append("---")
    parts.append("")


def _write_toc(parts: list[str], tree: list[HierarchyNode]) -> None:
    """生成简单的页码目录。"""
    parts.append("## 目录\n")

    def _walk(node: HierarchyNode, indent: int = 0):
        prefix = "  " * indent
        parts.append(f"{prefix}- {node.title}")
        for child in node.children:
            _walk(child, indent + 1)

    for node in tree:
        _walk(node)
    parts.append("")
    parts.append("---")
    parts.append("")


def _render_node(
    parts: list[str],
    node: HierarchyNode,
    *,
    article_anchor: bool,
) -> None:
    """递归渲染一个节点及其子节点。"""
    # 标题行
    heading = node.markdown_heading()
    if heading:
        parts.append(heading)
        parts.append("")

    # 正文内容
    if node.text:
        parts.append(node.text)
        parts.append("")

    # anchor 注释（仅在 ARTICLE 级别添加）
    if article_anchor and node.level == Level.ARTICLE and node.number:
        anchor_id = f"article-{node.number}"
        # 尝试用中文转写为易读的 anchor
        parts.append(f"<!-- anchor: {anchor_id} -->")
        parts.append("")

    # 子节点（递归）
    for child in node.children:
        _render_node(parts, child, article_anchor=article_anchor)

