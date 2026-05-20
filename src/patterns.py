"""法律文档结构正则模式库。

所有正则都预编译为 `re.Pattern`，按层级/用途分组。
支持标准法规模式和扩展模式（如"之一"、"第X条之二"）。
"""

import re


# ── 结构标题模式 ──────────────────────────────────────────

# 编: "第一编" "第二编"
RE_PART = re.compile(r"^第[一二三四五六七八九十百千]+编")

# 章: "第一章" "第十二章"
RE_CHAPTER = re.compile(r"^第[一二三四五六七八九十百千]+章")

# 节: "第一节" "第二十节"
RE_SECTION = re.compile(r"^第[一二三四五六七八九十百千]+节")

# 条（标准 + 扩展）：
#   "第一条" "第十二条" "第一百二十条"
#   "第一条之一" "第十二条之二" "第十二条之三"
#   NOT: "第一条文" "第一条款"（须有自然边界）
RE_ARTICLE = re.compile(
    r"^第([一二三四五六七八九十百千零]+)条(之[一二三四五六七八九十百千]+)?(?=\s|[，。,.\n]|$)"
)

# 款（自然段 - 通过缩进/空白行判断，正则只辅助）
# 项： "(一)" "(二)" "（一）" "（二）"
RE_SUB_CLAUSE_PAREN = re.compile(r"^[（(][一二三四五六七八九十百千]+[）)]")

# 项： "1." "2." "（1）" "（2）"
RE_SUB_CLAUSE_NUM = re.compile(r"^[（(]?\d+[．.、）)]")

# 目： "A." "a." "(a)" 或 "1)" 等更深层缩进
RE_ITEM = re.compile(r"^[（(]?[a-zA-Z][）)]|(?<=\s)\d+\)")

# ── 混合匹配（一次判断是哪级）─────────────────────────────

# 按优先级从高到低排列
# key 与 models.Level 枚举的 value 一致
LEVEL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("part", re.compile(r"^第[一二三四五六七八九十百千]+编\b")),
    ("chapter", re.compile(r"^第[一二三四五六七八九十百千]+章\b")),
    ("section", re.compile(r"^第[一二三四五六七八九十百千]+节\b")),
    ("article", RE_ARTICLE),
    ("sub_clause", RE_SUB_CLAUSE_PAREN),
    ("sub_clause", RE_SUB_CLAUSE_NUM),
    ("item", RE_ITEM),
]


def detect_level(text: str) -> str:
    """检测一行文本的法律层级，返回 level key 或空字符串。"""
    for key, pat in LEVEL_PATTERNS:
        if pat.match(text):
            return key
    return ""


# ── 元数据模式 ──────────────────────────────────────────

# 文号: "第XX号"（阿拉伯/中文数字）或 "XXX〔2020〕XX号"
_CN_DIGITS = r"[一二三四五六七八九十百千零]+"
RE_DOC_ID = re.compile(
    rf"(第\s*(?:\d+|{_CN_DIGITS})\s*号|"
    r".*?[〔（]\d{4}[〕）]\s*\d+\s*号)"
)

# 发布日期 / 施行日期
# "2020年5月28日" "2021年1月1日"
RE_DATE = re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日")

# 制定机关： "全国人民代表大会" "国务院" 等
RE_AUTHORITY = re.compile(
    r"(全国人民代表大会[常务委员会]?|"
    r"国务院|"
    r"最高人民法院|"
    r"最高人民检察院|"
    r"国家[^的]+局|"
    r"中华人民共和国[^的]+部)"
)

# 法规名称：第一页通常最大字号的第一行
# （不使用扫描直接识别模式，由结构识别引擎结合字号判断）

# ── 页眉/页脚过滤 ──────────────────────────────────────

# 常见页眉重复内容
RE_HEADER_FOOTER = re.compile(
    r"^[-—·•]+\s*\d+\s*[-—·•]+$|"       # "— 12 —"
    r"^\s*\d+\s*$|"                       # 纯页码
    r"^第\s*\d+\s*页$"                     # "第 12 页"
)

# ── 辅助 ──────────────────────────────────────────────────

def strip_article_number(text: str) -> str:
    """从条文中去掉'第X条'前缀，返回剩余文本。"""
    m = RE_ARTICLE.match(text)
    if m:
        return text[m.end():].strip()
    return text


def parse_article_number(text: str) -> str:
    """提取条号数字（中文），如 '第一条' → '一'。"""
    m = RE_ARTICLE.match(text)
    if m:
        return m.group(1)
    return ""
