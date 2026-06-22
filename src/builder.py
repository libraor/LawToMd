"""Markdown 组装层。

将 HierarchyNode 树转换为完整的 Markdown 文档。
支持法律法规和判决书两种文档类型的差异化输出。
"""

from __future__ import annotations

import re

from src.models import DocType, HierarchyNode, LawMeta, Level
from src.patterns import RE_LAW_REFERENCE


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


def _yaml_escape(value: str) -> str:
    """对 YAML 值进行安全转义，使用 yaml.safe_dump 确保正确性。"""
    if not value:
        return '""'
    import yaml
    # safe_dump 会自动处理引号和特殊字符，strip 去掉末尾换行
    result = yaml.safe_dump(value, allow_unicode=True, default_style=None).strip()
    # safe_dump 对字符串默认不加引号，但含特殊字符时会自动加
    # 如果结果以 | 或 > 开头（块标量），改为双引号风格
    if result.startswith(("|", ">")):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    return result


def _write_metadata_header(parts: list[str], meta: LawMeta) -> None:
    """写入 YAML-like 元数据头，根据文档类型输出不同字段。"""
    parts.append("---")
    if meta.name:
        parts.append(f"title: {_yaml_escape(meta.name)}")
    if meta.doc_id:
        parts.append(f"doc_id: {_yaml_escape(meta.doc_id)}")
    if meta.publish_date:
        parts.append(f"publish_date: {_yaml_escape(meta.publish_date)}")
    if meta.effective_date:
        parts.append(f"effective_date: {_yaml_escape(meta.effective_date)}")
    if meta.issuing_authority:
        parts.append(f"authority: {_yaml_escape(meta.issuing_authority)}")
    if meta.source_pdf:
        parts.append(f"source: {_yaml_escape(meta.source_pdf)}")

    # 文档类型
    if meta.doc_type != DocType.UNKNOWN:
        parts.append(f"doc_type: {meta.doc_type.value}")

    # 判决书特有元数据
    if meta.doc_type == DocType.JUDGMENT:
        if "case_number" in meta.extra:
            parts.append(f"case_number: {_yaml_escape(meta.extra['case_number'])}")
        if "court" in meta.extra:
            parts.append(f"court: {_yaml_escape(meta.extra['court'])}")
        if "judgment_type" in meta.extra:
            parts.append(f"judgment_type: {_yaml_escape(meta.extra['judgment_type'])}")
        if "judgment_date" in meta.extra:
            parts.append(f"judgment_date: {_yaml_escape(meta.extra['judgment_date'])}")

    # 书籍特有元数据
    if meta.doc_type == DocType.BOOK:
        if "author" in meta.extra:
            parts.append(f"author: {_yaml_escape(meta.extra['author'])}")
        if "publisher" in meta.extra:
            parts.append(f"publisher: {_yaml_escape(meta.extra['publisher'])}")
        if "isbn" in meta.extra:
            parts.append(f"isbn: {_yaml_escape(meta.extra['isbn'])}")
        if "publish_date" in meta.extra:
            parts.append(f"book_date: {_yaml_escape(meta.extra['publish_date'])}")

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
        # 脚注用小字标记
        if node.level == Level.FOOTNOTE:
            parts.append(f"<small>{node.text}</small>")
            parts.append("")
        else:
            parts.append(node.text)
            parts.append("")

    # anchor 注释（仅在 ARTICLE 级别添加）
    if article_anchor and node.level == Level.ARTICLE and node.number:
        anchor_id = f"article-{node.number}"
        parts.append(f"<!-- anchor: {anchor_id} -->")
        parts.append("")

    # 法律引用标注：生成 Markdown 链接
    if node.law_references:
        ref_links = []
        for ref in node.law_references:
            link = _reference_to_link(ref)
            ref_links.append(link)
        parts.append("引用: " + ", ".join(ref_links))
        parts.append("")

    # 子节点（递归）
    for child in node.children:
        _render_node(parts, child, article_anchor=article_anchor)


def _reference_to_link(ref: str) -> str:
    """将法律引用文本转换为 Markdown 链接。

    例如：'《民法典》第一百四十三条' → '[《民法典》第一百四十三条](#article-一百四十三)'

    如果无法解析条号，则返回纯文本。
    """
    m = RE_LAW_REFERENCE.match(ref)
    if m:
        # m.group(0) 包含 "《XXX》第X条" 部分
        full_match = m.group(0)
        # 提取条号部分（"第X条"中的X）
        article_part = re.search(r"第([一二三四五六七八九十百千零0-9]+)条", full_match)
        if article_part:
            article_num = article_part.group(1)
            return f"[{ref}](#article-{article_num})"
    return ref
