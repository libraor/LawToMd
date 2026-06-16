"""LawToMd 数据模型。

定义整个流水线的数据结构：
- LineMeta:      pdfplumber 提取的原始行，含坐标/字体信息
- LawMeta:       法规级元数据（名称、文号、日期等）
- JudgmentMeta:  判决书元数据（案号、法院、当事人等）
- HierarchyNode: 层级节点（编/章/节/条/款/项）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── 层级枚举 ──────────────────────────────────────────────

class Level(Enum):
    """法律结构层级枚举，从高到低。"""
    PART = "part"          # 编
    CHAPTER = "chapter"    # 章
    SECTION = "section"    # 节
    ARTICLE = "article"    # 条
    CLAUSE = "clause"      # 款（自然段）
    SUB_CLAUSE = "sub"     # 项
    ITEM = "item"          # 目

    # 判决书专用层级
    PARTY = "party"              # 当事人信息
    PROCEDURE = "procedure"      # 诉讼记录
    RULING = "ruling"            # 裁判结果
    JUDGES = "judges"            # 审判人员署名

    def heading_level(self) -> int:
        """映射到 Markdown 标题层级。"""
        return {
            Level.PART: 1,
            Level.CHAPTER: 2,
            Level.SECTION: 3,
            Level.ARTICLE: 4,
            Level.PARTY: 3,
            Level.PROCEDURE: 3,
            Level.RULING: 3,
            Level.JUDGES: 3,
        }.get(self, 0)  # 0 = 正文段落，不做标题

    def sort_order(self) -> int:
        """层级排序值（越小越上层），用于建树时的优先级比较。"""
        return {
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
        }.get(self, 99)

    @classmethod
    def from_label(cls, label: str) -> Optional["Level"]:
        for kw, lvl in [
            ("编", Level.PART),
            ("章", Level.CHAPTER),
            ("节", Level.SECTION),
            ("条", Level.ARTICLE),
        ]:
            if label.startswith("第") and kw in label:
                return lvl
        return None


# ── 文档类型枚举 ──────────────────────────────────────────

class DocType(Enum):
    """文档类型枚举。"""
    LAW = "law"                          # 法律法规
    JUDGMENT = "judgment"                # 判决书/裁定书
    INTERPRETATION = "interpretation"    # 司法解释
    UNKNOWN = "unknown"


# ── 原始行 ────────────────────────────────────────────────

@dataclass
class LineMeta:
    """pdfplumber 提取的一行文本及其排版信息。"""
    text: str
    page_num: int
    x0: float
    y0: float
    x1: float
    y1: float
    font_size: float = 0.0
    bold: bool = False
    fontname: str = ""
    is_table: bool = False


# ── 法规元数据 ────────────────────────────────────────────

@dataclass
class LawMeta:
    """从 PDF 头部抽取的法规级元数据。"""
    name: str = ""                     # 法规名称
    doc_id: str = ""                   # 文号（如"第XX号"）
    publish_date: str = ""             # 发布日期
    effective_date: str = ""           # 施行日期
    issuing_authority: str = ""        # 制定机关
    source_pdf: str = ""               # 源文件路径
    doc_type: DocType = DocType.UNKNOWN  # 文档类型
    extra: dict = field(default_factory=dict)


# ── 判决书元数据 ──────────────────────────────────────────

@dataclass
class JudgmentMeta:
    """从判决书 PDF 中抽取的元数据。"""
    case_number: str = ""              # 案号
    court: str = ""                    # 审理法院
    judgment_type: str = ""            # 文书类型（判决书/裁定书/调解书等）
    parties: list[str] = field(default_factory=list)  # 当事人列表
    judges: list[str] = field(default_factory=list)   # 审判人员
    clerk: str = ""                    # 书记员
    judgment_date: str = ""            # 裁判日期
    source_pdf: str = ""               # 源文件路径
    extra: dict = field(default_factory=dict)


# ── 层级节点 ──────────────────────────────────────────────

@dataclass
class HierarchyNode:
    """解析后的法律结构节点。

    一条法律条文或结构标题。Leaf = Article 或 Clause，
    但所有层级统一用此结构表示。
    """
    level: Level                         # 层级类型
    number: str = ""                     # 编号，如 "12"、"一"
    title: str = ""                      # 标题文本（含编号）
    text: str = ""                       # 正文内容（不含标题）
    hierarchy_path: list[str] = field(default_factory=list)
    # ↑ ["第一编 总则", "第一章 基本原则", "第十二条"]
    parent: Optional["HierarchyNode"] = field(default=None, repr=False)
    children: list["HierarchyNode"] = field(default_factory=list)
    page_num: int = 0
    law_references: list[str] = field(default_factory=list)
    # ↑ 该节点中引用的法律条文，如 ["《民法典》第一百四十三条"]

    def full_text(self) -> str:
        """标题+正文的合并文本。"""
        if self.title and self.text:
            return f"{self.title}\n{self.text}"
        return self.title or self.text

    def markdown_heading(self) -> str:
        """生成 Markdown 标题行（如果是有标题层级的话）。"""
        h = self.level.heading_level()
        if h > 0:
            return f"{'#' * h} {self.title}"
        return ""

    def hierarchy_str(self) -> str:
        """层级路径字符串，如 '第一编 总则 > 第一章 基本规定'。"""
        return " > ".join(self.hierarchy_path) if self.hierarchy_path else self.title
