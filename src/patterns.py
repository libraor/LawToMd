"""法律文档结构正则模式库。

所有正则都预编译为 `re.Pattern`，按层级/用途分组。
支持标准法规模式和扩展模式（如"之一"、"第X条之二"）。

覆盖文档类型：
- 法律法规（编/章/节/条/款/项/目）
- 司法解释（法释〔YYYY〕XX号）
- 法院判决书（当事人/诉讼记录/裁判文书）
"""

import re


# ── 中文数字字符集 ────────────────────────────────────────

_CN_DIGITS = "一二三四五六七八九十百千零"
_CN_DIGITS_PATTERN = rf"[{_CN_DIGITS}]+"

# 阿拉伯数字（用于混合编号场景）
_ARABIC_NUM = r"\d+"


# ── 结构标题模式 ──────────────────────────────────────────

# 编: "第一编" "第二编"
RE_PART = re.compile(rf"^第{_CN_DIGITS_PATTERN}编")

# 章: "第一章" "第十二章"
RE_CHAPTER = re.compile(rf"^第{_CN_DIGITS_PATTERN}章")

# 节: "第一节" "第二十节"
RE_SECTION = re.compile(rf"^第{_CN_DIGITS_PATTERN}节")

# 条（标准 + 扩展）：
#   "第一条" "第十二条" "第一百二十条"
#   "第一条之一" "第十二条之二" "第十二条之三"
#   NOT: "第一条文" "第一条款"（须有自然边界）
RE_ARTICLE = re.compile(
    rf"^第({_CN_DIGITS_PATTERN})条(之{_CN_DIGITS_PATTERN})?(?=\s|[，。,.\n]|$)"
)

# 款（自然段 - 通过缩进/空白行判断，正则只辅助）
# 项： "(一)" "(二)" "（一）" "（二）"
RE_SUB_CLAUSE_PAREN = re.compile(rf"^[（(][{_CN_DIGITS}]+[）)]")

# 项： "1." "2." "（1）" "（2）"
RE_SUB_CLAUSE_NUM = re.compile(rf"^[（(]?{_ARABIC_NUM}[．.、）)]")

# 目： "A." "a." "(a)" 或 "1)" 等更深层缩进
RE_ITEM = re.compile(r"^[（(]?[a-zA-Z][）)]|(?<=\s)\d+\)")

# ── 判决书结构模式 ────────────────────────────────────────

# 判决书标题：法院名称 + 判决书类型
RE_JUDGMENT_TITLE = re.compile(
    r"^(中华人民共和国)?"
    r"(.+?人民法院)"
    r"(民事|刑事|行政|赔偿|执行)"
    r"(判决书|裁定书|调解书|决定书|通知书)$"
)

# 当事人信息：原告/被告/第三人
RE_PARTY = re.compile(
    r"^(原告|被告|第三人|上诉人|被上诉人|申请人|被申请人|再审申请人|原审原告|原审被告)"
    r"[：:]"
)

# 诉讼记录段落标记
RE_PROCEDURE_HEADER = re.compile(
    r"^(原告|被告|第三人|上诉人|被上诉人).+?诉称|"
    r"^(本院|法院)(依法|于|经)?(组成|公开|审理|查明)"
)

# 裁判结果段落标记
RE_RULING_HEADER = re.compile(
    r"^(依照|根据).+?(规定|判决|裁定|决定)如下[：:]?|"
    r"^判决如下[：:]?|"
    r"^裁定如下[：:]?|"
    r"^决定如下[：:]?"
)

# 审判人员署名
RE_JUDGES = re.compile(
    r"^(审判长|审判员|代理审判员|陪审员|法官助理|书记员)[：:]?\s*\S"
)

# ── 法律引用标注模式 ──────────────────────────────────────

# 法条引用："《XXX》第X条" "《XXX》第X条第X款"
RE_LAW_REFERENCE = re.compile(
    rf"《[^》]+》第{_CN_DIGITS_PATTERN}条"
    rf"(第{_CN_DIGITS_PATTERN}款)?"
    rf"(第{_CN_DIGITS_PATTERN}项)?"
)

# 司法解释引用："法释〔2020〕1号" "法释〔2020〕1号第3条"
RE_JUDICIAL_INTERPRETATION = re.compile(
    r"法释[〔（]\d{4}[〕）]\s*\d+\s*号"
)

# 法律名称引用：《中华人民共和国XXX法》
RE_LAW_TITLE = re.compile(
    r"《[^》]+?(?:法|条例|规定|办法|决定|意见|规则|细则|通则|解释|批复|答复)》"
)

# ── 混合匹配（一次判断是哪级）─────────────────────────────

# 按优先级从高到低排列
# key 与 models.Level 枚举的 value 一致
LEVEL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("part", re.compile(rf"^第{_CN_DIGITS_PATTERN}编\b")),
    ("chapter", re.compile(rf"^第{_CN_DIGITS_PATTERN}章\b")),
    ("section", re.compile(rf"^第{_CN_DIGITS_PATTERN}节\b")),
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


# ── 文档类型检测 ──────────────────────────────────────────

class DocType:
    """文档类型常量。"""
    LAW = "law"                    # 法律法规
    JUDGMENT = "judgment"          # 判决书/裁定书
    INTERPRETATION = "interpretation"  # 司法解释
    UNKNOWN = "unknown"


def detect_doc_type(text: str) -> str:
    """根据首页文本判断文档类型。

    Parameters
    ----------
    text : str
        首页文本内容。

    Returns
    -------
    str
        DocType 常量之一。
    """
    # 判决书：含法院名称 + 判决书类型
    if RE_JUDGMENT_TITLE.search(text):
        return DocType.JUDGMENT

    # 司法解释：含"法释〔YYYY〕XX号"
    if RE_JUDICIAL_INTERPRETATION.search(text):
        return DocType.INTERPRETATION

    # 法律法规：含编/章/节/条结构
    if detect_level(text):
        return DocType.LAW

    return DocType.UNKNOWN


# ── 元数据模式 ──────────────────────────────────────────

# 文号: "第XX号"（阿拉伯/中文数字）或 "XXX〔2020〕XX号"
RE_DOC_ID = re.compile(
    rf"(第\s*(?:{_ARABIC_NUM}|{_CN_DIGITS_PATTERN})\s*号|"
    r".*?[〔（]\d{4}[〕）]\s*\d+\s*号)"
)

# 发布日期 / 施行日期
# "2020年5月28日" "2021年1月1日"
RE_DATE = re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日")

# 制定机关： "全国人民代表大会" "国务院" 等
RE_AUTHORITY = re.compile(
    r"(全国人民代表大会(常务委员会)?|"
    r"国务院|"
    r"最高人民法院|"
    r"最高人民检察院|"
    r"国家[^的]+局|"
    r"中华人民共和国[^的]+部|"
    r"中华人民共和国[^的]+委员会|"
    r"中华人民共和国[^的]+署|"
    r"中华人民共和国[^的]+院)"
)

# 案号："（2020）京01民初1号" "(2020)最高法民申123号"
RE_CASE_NUMBER = re.compile(
    r"[（(]\s*\d{4}\s*[）)]\s*[\u4e00-\u9fff\d]+\d+号"
)

# 法规名称：第一页通常最大字号的第一行
# （不使用扫描直接识别模式，由结构识别引擎结合字号判断）

# ── 页眉/页脚过滤 ──────────────────────────────────────

# 常见页眉重复内容
RE_HEADER_FOOTER = re.compile(
    r"^[-—·•]+\s*\d+\s*[-—·•]+$|"       # "— 12 —"
    r"^\s*\d+\s*$|"                       # 纯页码
    r"^第\s*\d+\s*页$|"                    # "第 12 页"
    r"^\s*第\s*\d+\s*页\s*共\s*\d+\s*页$"  # "第 12 页 共 34 页"
)

# ── 中文数字转换 ──────────────────────────────────────────

_CN_DIGIT_MAP = {
    "零": 0, "〇": 0,
    "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8,
    "九": 9, "十": 10, "百": 100, "千": 1000,
}


def cn_to_arabic(cn: str) -> int:
    """将中文数字转换为阿拉伯数字。

    支持范围：零 至 九千九百九十九。

    Examples:
        >>> cn_to_arabic("一")
        1
        >>> cn_to_arabic("十二")
        12
        >>> cn_to_arabic("一百二十三")
        123
        >>> cn_to_arabic("一千零一")
        1001
    """
    if not cn:
        return 0

    # 纯阿拉伯数字直接返回
    if cn.isdigit():
        return int(cn)

    result = 0
    current = 0

    for ch in cn:
        val = _CN_DIGIT_MAP.get(ch)
        if val is None:
            continue
        if val >= 10:
            if current == 0:
                current = 1
            result += current * val
            current = 0
        else:
            current = val

    result += current
    return result


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


def extract_law_references(text: str) -> list[str]:
    """提取文本中的法律引用标注。

    Returns
    -------
    list[str]
        所有匹配的法律引用，如 '《民法典》第一百四十三条'。
    """
    return RE_LAW_REFERENCE.findall(text)
