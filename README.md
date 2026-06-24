# LawToMd

**法律文档 PDF → Markdown 转换工具**，面向批量化法律文档处理。

自动识别法律文档特有的 **编 → 章 → 节 → 条 → 款 → 项 → 目** 层级结构，支持法律法规、判决书、司法解释、法律书籍等多种文档类型，输出结构化 Markdown 或 JSON。

---

## 适用场景

- **法律知识库构建** — 批量处理整套法规体系，生成结构化文档
- **判决书电子化** — 将法院判决书、裁定书转换为结构化 Markdown
- **司法解释归档** — 处理司法解释、批复、答复等文档
- **法律书籍电子化** — 将法律教材、专著、工具书转换为结构化文档，保留前言/后记/脚注
- **法条对比分析** — 新旧法规条文级别的差异比对
- **LLM 微调数据准备** — 清洗、结构化后的高质量法律语料
- **法律引用分析** — 自动提取文档中的法律引用标注（如"《民法典》第一百四十三条"）

---

## 功能

- 📄 **PDF 文本提取** — 基于 pdfplumber，保留坐标、字号、加粗等信息，过滤页眉页脚
- 🔍 **OCR 支持** — 统一 OCR API 接口，支持百度、阿里云、腾讯云等云端 OCR 服务
- 🏛 **多文档类型支持** — 自动检测并适配法律法规、判决书、司法解释、法律书籍的结构解析策略
- ⚖️ **法律术语识别** — 覆盖编/章/节/条/款/项/目结构，当事人/诉讼记录/裁判结果等判决书元素
- � **书籍结构识别** — 前言/序言/章/节/小节/正文+脚注/附录/后记完整链路
- �🔗 **引用标注提取** — 自动识别并输出法律引用（`《XXX》第X条第X款第X项`），自动转为锚点链接
- 📝 **结构化输出** — YAML 元数据头 + 层级标题 + anchor 注释 + 引用标注（Markdown / JSON）
- ⚡ **批量并行处理** — 递归扫描目录，`--workers` 控制并发数，自动显示进度条
- 🧹 **文本规范化** — 全角空格统一、OCR 误识别修正、自定义替换规则（`config/replace.yaml`）
- ✅ **条号校验** — `--validate` 检测缺失条号，保障输出完整性
- 📊 **表格提取** — 自动将 PDF 表格转为 Markdown 表格
- 🔧 **可配置** — 页眉页脚过滤、目录生成、anchor 注释、OCR 引擎选择均可调

---

## 安装

```bash
# 从源码安装（核心功能，不含 OCR）
git clone https://github.com/YOUR_ORG/lawtomd.git
cd lawtomd
pip install -e .

# 安装 OCR API 依赖（含云端 OCR 支持）
pip install -e ".[ocr]"

# 确认安装
lawtomd --help
```

**核心依赖**：`pdfplumber` (PDF 解析引擎)、`click` (CLI 框架)、`pyyaml` (配置文件解析)。

**系统要求**：Python >=3.10, <=3.13

---

## OCR 配置

LawToMd 使用 **第三方 OCR API** 作为 OCR 后端，通过 HTTP 调用云端 OCR 服务。支持百度、阿里云、腾讯云及自定义 API 端点。

### 配置文件

编辑 [config/ocr_api.yaml](config/ocr_api.yaml)：

```yaml
# API 端点地址
api_url: "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic"

# API 密钥
api_key: "your-api-key-here"

# 提供商: baidu / aliyun / tencent / custom
provider: "baidu"
```

### 支持的提供商

| 提供商 | 说明 |
|--------|------|
| `baidu` | 百度 AI 开放平台 — 通用文字识别 |
| `aliyun` | 阿里云视觉智能 — 文字识别 |
| `tencent` | 腾讯云 OCR — 通用印刷体识别 |
| `custom` | 自定义 API 端点，需配置请求/响应模板 |

### 使用方式

```bash
# 1. 编辑 config/ocr_api.yaml 填入 API Key

# 2. 自动 OCR 模式（无文字页面回退到 OCR）
lawtomd convert 扫描件.pdf --ocr auto

# 强制所有页面使用 OCR
lawtomd convert 扫描件.pdf --ocr force

# 使用 verbose 查看日志
lawtomd -vv convert 扫描件.pdf --ocr auto
```

### 切换后端

通过环境变量控制：

```bash
# 使用 OCR API 后端（默认）
lawtomd convert input.pdf --ocr auto

# 禁用 OCR
lawtomd convert input.pdf --ocr off
```

---

## 快速开始

```bash
# 单文件转换
lawtomd convert 民法典.pdf

# 对扫描件自动启用 OCR
lawtomd convert 扫描件.pdf --ocr auto

# 强制所有页面使用 OCR
lawtomd convert 扫描件.pdf --ocr force

# 输出结构化 JSON
lawtomd convert 民法典.pdf --format json

# 校验条号连续性
lawtomd convert 民法典.pdf --validate

# 批量处理一批法规（并行）
lawtomd batch ./法规目录/ -o ./output/

# 查看设备状态
lawtomd profile
```

---

## CLI 参考

### 全局选项

| 选项 | 说明 |
|------|------|
| `-v` | 增加日志详细度（-v INFO, -vv DEBUG） |
| `--help` | 查看命令帮助 |

### `convert` — 单文件转换

```bash
lawtomd convert <PDF_PATH> [选项]
```

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `-o, --output` | 同文件名 `.md` | 输出路径 |
| `--max-pages` | 全部 | 只处理前 N 页 |
| `--no-filter` | 过滤 | 不过滤页眉页脚 |
| `--toc` | 不生成 | 在 Markdown 开头生成目录 |
| `--no-anchor` | 生成 | 不添加 `<!-- anchor -->` 注释 |
| `--ocr` | `off` | OCR 模式: `auto`=对无文字页面回退, `force`=强制所有页面, `off`=禁用 |
| `--format` | `md` | 输出格式: `md`=Markdown, `json`=结构化JSON |
| `--validate` | 不校验 | 校验条号连续性，检测缺失条号 |

**示例：**

```bash
# 基础转换
lawtomd convert 民法典.pdf

# 指定输出路径
lawtomd convert 民法典.pdf -o output/民法典.md

# 预览前 10 页
lawtomd convert 民法典.pdf --max-pages 10

# OCR 自动模式
lawtomd convert 扫描件.pdf --ocr auto

# 输出结构化 JSON
lawtomd convert 民法典.pdf --format json

# 校验条号连续性
lawtomd convert 民法典.pdf --validate
```

### `batch` — 批量处理

```bash
lawtomd batch <PDF_DIR> [选项]
```

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `-o, --output` | `./output/` | 输出目录 |
| `--max-pages` | 全部 | 每份 PDF 只处理前 N 页 |
| `--flatten` | 不展开 | 扁平化到单层目录 |
| `--no-filter` | 过滤 | 不过滤页眉页脚 |
| `--ocr` | `off` | OCR 模式: `auto`/`force`/`off` |
| `--workers` | CPU 核心数 | 并行处理文件数 |

**示例：**

```bash
# 批量转换（默认并行）
lawtomd batch ./pdfs/ -o ./output/

# 扁平化输出（所有 .md 在同一目录）
lawtomd batch ./pdfs/ -o ./output/ --flatten

# 批量 OCR
lawtomd batch ./pdfs/ -o ./output/ --ocr auto

# 并行处理（8 个并发）
lawtomd batch ./pdfs/ -o ./output/ --workers 8
```

### `profile` — 设备状态检测

```bash
lawtomd profile
```

显示当前 OCR API 配置状态和依赖安装情况。

---

## 输出格式

每条法规输出一个 `.md`（或 `.json`）文件，包含 YAML 元数据头、层级标题、正文和 anchor 注释：

### 法律法规示例

```markdown
---
title: 中华人民共和国民法典
doc_id: 中华人民共和国主席令第四十五号
publish_date: 2020年5月28日
effective_date: 2021年1月1日
authority: 全国人民代表大会
source: 民法典.pdf
doc_type: law
---

# 第一编 总则

## 第一章 基本规定

#### 第一条 为了保护民事主体的合法权益
调整民事关系，维护社会和经济秩序…

<!-- anchor: article-一 -->

#### 第十二条 中华人民共和国领域内的民事活动
适用中华人民共和国法律。

<!-- anchor: article-十二 -->
```

### 判决书示例

```markdown
---
title: 北京市朝阳区人民法院民事判决书
doc_id:
case_number: （2023）京0105民初12345号
court: 北京市朝阳区人民法院
judgment_type: 民事判决书
source: 判决书.pdf
doc_type: judgment
---

### 原告张三：男，1980年出生...

本院经审理查明...

### 本院认为
被告的行为构成违约...

### 判决如下：
一、被告于本判决生效之日起十日内支付原告...
二、驳回原告其他诉讼请求...
```

### 法律书籍示例

```markdown
---
title: 要件审判九步法
author: 邹碧华
publisher: 法律出版社
isbn: 978-7-5118-XXXX-X
publish_date: 2014年
source: 要件审判九步法.pdf
doc_type: book
---

# 序言

# 第一章 诉讼请求的固定

## 一、诉讼请求的分类

审判实践中，诉讼请求主要分为以下几类……

<small>① 参见《民事诉讼法》第119条。</small>
```

---

## 支持的文档类型

| 类型 | 自动检测依据 | 解析策略 |
|------|-------------|---------|
| **法律法规** | 含编/章/节/条结构 | 编→章→节→条→款→项→目 |
| **判决书/裁定书** | 含"法院名称+民事/刑事/行政+判决书" | 当事人→诉讼记录→裁判结果→审判人员 |
| **司法解释** | 含"法释〔YYYY〕XX号" | 按法规结构解析 |
| **法律书籍** | 含前言/序言/出版社/ISBN | 前言→章→节→小节→正文+脚注→附录/后记 |
| **其他法律文档** | 无上述特征 | 回退到通用编/章/节/条解析 |

---

## 架构

```
                ╭─────────────────────╮
PDF 文件 ─────→│    extractor.py     │── → LineMeta[]
                │ pdfplumber 文本+坐标  │
                │    + OCR 调度       │
                ╰─────────┬───────────╯
                          ↓
                ╭─────────────────────╮
                │    structure.py     │── → HierarchyNode 树
                │ 正则 + 状态机识别层级 │
                ╰─────────┬───────────╯
                          ↓
                ╭─────────────────────╮
                │     builder.py      │── → 完整 Markdown / JSON
                │ YAML 头 + 标题 +正文 │
                ╰─────────────────────╯
```

### 模块职责

| 模块 | 文件 | 核心职责 |
|------|------|----------|
| 数据模型 | `models.py` | LineMeta / LawMeta / JudgmentMeta / BookMeta / HierarchyNode / DocType 定义 |
| 模式库 | `patterns.py` | 30+ 预编译正则，覆盖编/章/节/条/当事人/裁判结果/法律引用/案号/脚注等 |
| 文本提取 | `extractor.py` | 双策略提取、页眉页脚过滤、OCR 调度、表格提取、文档类型检测 |
| 文本规范化 | `normalizer.py` | 全角空格统一、OCR 误识别修正、自定义替换规则 |
| 页眉页脚过滤 | `header_footer.py` | 标准模式 + 自定义签名过滤 |
| 元数据提取 | `metadata.py` | 法规标题、文号、日期、颁布机关；书籍作者/出版社/ISBN 等 |
| 结构识别 | `structure.py` | 多策略解析（法规/判决书/书籍）、层级状态机、款缩进检测、子条款归并、引用提取 |
| Markdown 组装 | `builder.py` | YAML 元数据头（文档类型感知）、层级标题映射、anchor + 引用注释、JSON 输出 |
| OCR 调度器 | `ocr.py` | 统一 OcrEngine 单例接口，PDF 页面→图像渲染 |
| OCR API 后端 | `ocr_api.py` | 第三方 OCR API 调用（百度/阿里云/腾讯云/自定义），YAML 配置驱动 |
| 类型定义 | `types.py` | OcrBackendProtocol、OcrMode 等公共类型 |
| CLI 入口 | `main.py` | click 命令组（convert + batch + profile），支持 --format/--validate/--workers 选项 |

---

## 技术设计

### 层级识别算法

1. **文档类型检测**：根据首页文本自动判断法律法规/判决书/司法解释/法律书籍
2. **标题检测**：用正则判断文本行属于编/章/节/条（法规）或当事人/诉讼记录/裁判结果/审判人员（判决书）或章节小节（书籍）
3. **子条款检测**：`（一）`、`1.` 等模式匹配为项/目级别，挂在当前条下
4. **款缩进检测**：基于 x0 坐标偏移自动识别条下款（CLAUSE 层级）
5. **树构建**：维护一个层级栈，新节点按优先级找到正确父节点
6. **目录去重**：同标题且同层级的节点自动合并
7. **引用提取**：遍历树节点，提取所有法律引用标注并转为锚点链接

### OCR 架构

```
                    OcrEngine (单例)
                   ┌────────────────┐
                   │  OCR API 后端   │──→ config/ocr_api.yaml
                   │                │    ┌──────────────────┐
                   │  provider?     │──→ │ 百度 / 阿里云     │
                   │                │    │ 腾讯云 / 自定义   │
                   └────────────────┘    └──────────────────┘
```

- **单例模式**：全局复用 OcrEngine 实例，延迟初始化
- **配置驱动**：通过 `config/ocr_api.yaml` 统一管理 API 地址、密钥、请求/响应格式
- **多提供商**：内置百度/阿里云/腾讯云适配器，支持自定义端点

### 文本规范化

提取后的文本经过以下规范化处理：

| 处理项 | 示例 | 说明 |
|--------|------|------|
| 全角空格→半角 | `第一条  为了…` → `第一条 为了…` | 去除排版多余空格 |
| OCR 误识别修正 | `第0条` → `第十条` | 修正 0/O/l/I/1 混淆 |
| 自定义替换规则 | 见 `config/replace.yaml` | 常见法律术语拼写修正 |
| 页眉页脚过滤 | `第 12 页`、`— 12 —` | 标准模式 + 自定义签名 |
| 中文标点保留 | `，。：；（）` | 法律文本规范，不做全角→半角转换 |

### PDF 文本提取策略

pdfplumber 提供两种提取方式，按优先级尝试：

- **优先：** `page.extract_text_lines(return_chars=True)` — 直接获取行+字符级坐标
- **回退：** `page.extract_words()` → 按 y0 聚类 → 合并为行

提取结果保留：`(x0, y0, x1, y1)` 坐标、字号、是否加粗。

---

## 项目结构

```
LawToMd/
├── src/
│   ├── __init__.py
│   ├── main.py           # CLI 入口（convert + batch + profile）
│   ├── models.py         # 数据类
│   ├── patterns.py       # 正则模式库
│   ├── extractor.py      # PDF 文本提取 + OCR 调度 + 表格提取
│   ├── normalizer.py     # 文本规范化（全角空格/OCR 修正/替换规则）
│   ├── header_footer.py  # 页眉页脚过滤
│   ├── metadata.py       # 元数据提取（标题/文号/日期/机关/书籍信息）
│   ├── structure.py      # 结构识别引擎（款缩进检测/引用提取/书籍解析）
│   ├── builder.py        # Markdown/JSON 组装
│   ├── ocr.py            # OCR 引擎调度器（统一接口 + 单例）
│   ├── ocr_api.py        # 第三方 OCR API 后端（百度/阿里云/腾讯云）
│   └── types.py          # 公共类型定义（OcrBackendProtocol 等）
├── config/
│   ├── replace.yaml      # 常用词替换规则
│   └── ocr_api.yaml      # OCR API 配置（URL/密钥/提供商）
├── tests/
│   ├── conftest.py       # 测试夹具
│   ├── test_patterns.py  # 模式测试
│   ├── test_structure.py # 结构测试
│   ├── test_builder.py   # 构建测试
│   └── test_e2e.py       # 端到端测试
├── pyproject.toml
├── requirements.txt
├── README.md
└── CHANGELOG.md
```

---

## 开发

```bash
# 安装开发依赖
pip install pytest pytest-cov
pip install -e .

# 运行单元测试
pytest -v

# 带覆盖率
pytest --cov=src -v

# 端到端测试（需要先生成测试 PDF）
python tests/generate_test_pdf.py
python tests/test_e2e.py
```

### 测试覆盖

| 测试文件 | 覆盖范围 |
|----------|----------|
| `test_patterns.py` | 各级别正则匹配/不匹配、中文数字转换 |
| `test_structure.py` | 空输入、单条、多级、子条款、收集 |
| `test_builder.py` | 基础构建、多级、单条、无 anchor |
| `test_e2e.py` | 全流水线：提取→结构→Markdown |
