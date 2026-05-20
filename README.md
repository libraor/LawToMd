# LawToMd

**法律文档 PDF → Markdown 转换工具**，面向批量化法律文档处理。

自动识别法律文档特有的 **编 → 章 → 节 → 条 → 款 → 项 → 目** 层级结构，支持法律法规、判决书、司法解释等多种文档类型，输出结构化 Markdown。

---

## 适用场景

- **法律知识库构建** — 批量处理整套法规体系，生成结构化文档
- **判决书电子化** — 将法院判决书、裁定书转换为结构化 Markdown
- **司法解释归档** — 处理司法解释、批复、答复等文档
- **法条对比分析** — 新旧法规条文级别的差异比对
- **LLM 微调数据准备** — 清洗、结构化后的高质量法律语料
- **法律引用分析** — 自动提取文档中的法律引用标注（如"《民法典》第一百四十三条"）

---

## 功能

- 📄 **PDF 文本提取** — 基于 pdfplumber，保留坐标、字号、加粗等信息，过滤页眉页脚
- 🔍 **OCR 支持** — 可选 PaddleOCR 引擎，对扫描件/图片 PDF 自动识别（auto/force/off 三种模式）
- 🏛 **多文档类型支持** — 自动检测并适配法律法规、判决书、司法解释的结构解析策略
- ⚖️ **法律术语识别** — 覆盖编/章/节/条/款/项/目结构，当事人/诉讼记录/裁判结果等判决书元素
- 🔗 **引用标注提取** — 自动识别并输出法律引用（`《XXX》第X条第X款第X项`）
- 📝 **结构化 Markdown** — YAML 元数据头 + 层级标题 + anchor 注释 + 引用标注
- ⚡ **批量处理** — 递归扫描目录，保持子目录结构或扁平化输出
- 🧹 **文本规范化** — 全角空格统一、OCR 误识别修正、自定义替换规则（`config/replace.yaml`）
- 🔧 **可配置** — 页眉页脚过滤、目录生成、anchor 注释均可调

---

## 安装

```bash
# 从源码安装（核心功能）
git clone https://github.com/YOUR_ORG/lawtomd.git
cd lawtomd
pip install -e .

# 安装 OCR 支持（可选）
pip install -e ".[ocr]"

# 确认安装
lawtomd --help
```

**核心依赖**：`pdfplumber` (PDF 解析引擎)、`click` (CLI 框架)。

---

## OCR 配置要求

OCR 功能为可选依赖，通过 `pip install -e ".[ocr]"` 一并安装。

### 依赖清单

| 包 | 版本 | 用途 |
|---|---|---|
| `paddlepaddle` | 3.0.0 | 深度学习推理框架 |
| `paddleocr` | 2.10.0 | OCR 引擎（中文识别） |
| `opencv-contrib-python` | 4.13.0.92 | 图像预处理 |
| `PyMuPDF` | >=1.23.0 | PDF 页面→图像渲染 |
| `Pillow` | >=10.0 | 图像处理 |

### 系统要求

| 项目 | 要求 |
|---|---|
| **Python** | >=3.10, <=3.12 |
| **内存** | 建议 >=4GB（PaddleOCR 模型加载约占用 1-2GB） |
| **磁盘** | 首次运行自动下载中文识别模型（约 50MB） |
| **CPU** | 最低支持，默认单线程运行 |
| **GPU** | 可选（需安装 `paddlepaddle-gpu` 替代 `paddlepaddle`） |

### Windows 注意事项

- PaddleOCR 底层依赖 `torch` 的 DLL 加载，代码已内置 `_ensure_torch_dll_path()` 自动处理路径
- 如遇到 DLL 加载失败，可尝试安装 [Visual C++ Redistributable](https://learn.microsoft.com/zh-cn/cpp/windows/latest-downloads)
- OCR 模型首次启动时需下载缓存，请耐心等待

### 验证 OCR 可用

```bash
# 转换时启用自动 OCR 模式
lawtomd convert 扫描件.pdf --ocr auto

# 或使用 verbose 查看初始化日志
lawtomd -vv convert 扫描件.pdf --ocr auto
```

初始化成功会看到类似日志：

```
[INFO] src.ocr: PaddleOCR 引擎初始化完成 (CPU mode, single-thread)
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

# 批量处理一批法规
lawtomd batch ./法规目录/ -o ./output/
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

**示例：**

```bash
# 基础转换
lawtomd convert 民法典.pdf

# 指定输出路径
lawtomd convert 民法典.pdf -o output/民法典.md

# 预览前 10 页
lawtomd convert 民法典.pdf --max-pages 10
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

**示例：**

```bash
# 批量转换
lawtomd batch ./pdfs/ -o ./output/

# 扁平化输出（所有 .md 在同一目录）
lawtomd batch ./pdfs/ -o ./output/ --flatten
```

---

## 输出格式

每条法规输出一个 `.md` 文件，包含 YAML 元数据头、层级标题、正文和 anchor 注释：

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

---

## 支持的文档类型

| 类型 | 自动检测依据 | 解析策略 |
|------|-------------|---------|
| **法律法规** | 含编/章/节/条结构 | 编→章→节→条→款→项→目 |
| **判决书/裁定书** | 含"法院名称+民事/刑事/行政+判决书" | 当事人→诉讼记录→裁判结果→审判人员 |
| **司法解释** | 含"法释〔YYYY〕XX号" | 按法规结构解析 |
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
                │     builder.py      │── → 完整 Markdown
                │ YAML 头 + 标题 +正文 │
                ╰─────────────────────╯
```

### 模块职责

| 模块 | 文件 | 核心职责 |
|------|------|----------|
| 数据模型 | `models.py` | LineMeta / LawMeta / JudgmentMeta / HierarchyNode 定义 |
| 模式库 | `patterns.py` | 30+ 预编译正则，覆盖编/章/节/条/当事人/裁判结果/法律引用/案号等 |
| 文本提取 | `extractor.py` | 双策略提取、页眉页脚过滤、OCR 调度、文本规范化、文档类型检测 |
| 结构识别 | `structure.py` | 多策略解析（法规/判决书）、层级状态机、子条款归并、引用提取 |
| Markdown 组装 | `builder.py` | YAML 元数据头（文档类型感知）、层级标题映射、anchor + 引用注释 |
| OCR 引擎 | `ocr.py` | PaddleOCR 延迟初始化单例，PDF 页→图像渲染，坐标转换 |
| CLI 入口 | `main.py` | click 命令组（convert + batch），均支持 --ocr 选项 |

---

## 技术设计

### 层级识别算法

1. **文档类型检测**：根据首页文本自动判断法律法规/判决书/司法解释
2. **标题检测**：用正则判断文本行属于编/章/节/条（法规）或 当事人/诉讼记录/裁判结果/审判人员（判决书）
3. **子条款检测**：`（一）`、`1.` 等模式匹配为项/目级别，挂在当前条下
4. **树构建**：维护一个层级栈，新节点按优先级找到正确父节点
5. **目录去重**：同标题且无实质内容的节点自动合并
6. **引用提取**：遍历树节点，提取所有法律引用标注（`《XXX》第X条`）

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
│   ├── main.py           # CLI 入口
│   ├── models.py         # 数据类
│   ├── patterns.py       # 正则模式库
│   ├── extractor.py      # PDF 文本提取 + OCR 调度
│   ├── structure.py      # 结构识别引擎
│   ├── builder.py        # Markdown 组装
│   └── ocr.py            # PaddleOCR 引擎封装（可选依赖）
├── config/
│   └── replace.yaml      # 常用词替换规则
├── tests/
│   ├── conftest.py       # 测试夹具
│   ├── test_patterns.py  # 模式测试
│   ├── test_structure.py # 结构测试
│   ├── test_builder.py   # 构建测试
│   ├── test_ocr.py       # OCR 测试（需安装 OCR 依赖）
│   └── test_e2e.py       # 端到端测试
├── pyproject.toml
├── requirements.txt
└── README.md
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

| 测试文件 | 数量 | 覆盖范围 |
|----------|------|----------|
| `test_patterns.py` | 16 | 各级别正则匹配/不匹配、中文数字转换 |
| `test_structure.py` | 5 | 空输入、单条、多级、子条款、收集 |
| `test_builder.py` | 4 | 基础构建、多级、单条、无 anchor |
| `test_ocr.py` | 15 | OCR 转换、引擎初始化、PDF 提取 |
| `test_e2e.py` | 1 | 全流水线：提取→结构→Markdown |
