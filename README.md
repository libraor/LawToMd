# LawToMd

**法律文档 PDF → Markdown 转换工具**，面向批量化法律文档处理。

自动识别法律文档特有的 **编 → 章 → 节 → 条 → 款 → 项 → 目** 层级结构，支持法律法规、判决书、司法解释、法律书籍等多种文档类型，输出结构化 Markdown。

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
- 🔍 **OCR 支持** — 统一使用 PaddleOCR，自动检测 GPU 并启用加速
- 🏛 **多文档类型支持** — 自动检测并适配法律法规、判决书、司法解释的结构解析策略
- ⚖️ **法律术语识别** — 覆盖编/章/节/条/款/项/目结构，当事人/诉讼记录/裁判结果等判决书元素
- 🔗 **引用标注提取** — 自动识别并输出法律引用（`《XXX》第X条第X款第X项`）
- 📝 **结构化 Markdown** — YAML 元数据头 + 层级标题 + anchor 注释 + 引用标注
- ⚡ **批量处理** — 递归扫描目录，保持子目录结构或扁平化输出
- 🧹 **文本规范化** — 全角空格统一、OCR 误识别修正、自定义替换规则（`config/replace.yaml`）
- 🖥 **设备性能检测** — 自动评估 CPU/内存/GPU，推荐最优 OCR 方案
- 🔧 **可配置** — 页眉页脚过滤、目录生成、anchor 注释、OCR 引擎选择均可调

---

## 安装

```bash
# 从源码安装（核心功能，不含 OCR）
git clone https://github.com/YOUR_ORG/lawtomd.git
cd lawtomd
pip install -e .

# 安装 PaddleOCR（含 OCR 支持）
pip install -e ".[ocr]"

# 确认安装
lawtomd --help
```

**核心依赖**：`pdfplumber` (PDF 解析引擎)、`click` (CLI 框架)、`pyyaml` (配置文件解析)。

---

## OCR 配置

LawToMd 统一使用 **PaddleOCR** 作为唯一 OCR 后端，自动检测 GPU 并启用加速。

### PaddleOCR 依赖清单

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
| **Python** | >=3.10, <=3.13 |
| **内存** | 建议 >=4GB |
| **磁盘** | 首次运行自动下载模型（约 50MB） |
| **CPU** | 支持，默认单线程运行 |
| **GPU** | 可选（NVIDIA CUDA，自动检测并启用） |

### GPU 自动检测

LawToMd 启动时会自动检测设备性能：
- 检测到 NVIDIA 独立显卡 → PaddleOCR 启用 GPU 加速
- 无 GPU 或仅有集成显卡 → 以 CPU 模式运行

可通过 `lawtomd profile` 命令查看检测结果。

### Windows 注意事项

- PaddleOCR 底层依赖 `torch` 的 DLL 加载，代码已内置 `_ensure_torch_dll_path()` 自动处理路径
- 如遇到 DLL 加载失败，可尝试安装 [Visual C++ Redistributable](https://learn.microsoft.com/zh-cn/cpp/windows/latest-downloads)
- OCR 模型首次启动时需下载缓存，请耐心等待

### 验证 OCR 可用

```bash
# 查看设备性能检测
lawtomd profile

# 转换时启用自动 OCR 模式
lawtomd convert 扫描件.pdf --ocr auto

# 强制所有页面使用 OCR
lawtomd convert 扫描件.pdf --ocr force

# 使用 verbose 查看初始化日志
lawtomd -vv convert 扫描件.pdf --ocr auto
```

初始化成功会看到类似日志：

```
[INFO] src.ocr: OCR 引擎初始化: PaddleOCR (设备性能=high)
[INFO] src.ocr_paddle: PaddleOCR 引擎初始化完成 (GPU mode)
```

---

## Docker GPU 加速（推荐用于 RTX 50 系列）

针对 NVIDIA RTX 50 系列（Blackwell 架构）显卡，由于 PaddlePaddle 3.x 原生未完全支持 sm120 计算能力，**推荐使用官方 Docker 镜像**进行 GPU 加速。

### 前置要求

| 项目 | 要求 |
|------|------|
| **NVIDIA 驱动** | 支持 CUDA 12.9+ |
| **Docker Desktop** | 已安装并启动 |
| **NVIDIA Container Toolkit** | Docker Desktop 自带 WSL2 GPU 支持 |
| **NVIDIA GPU** | RTX 5060/5070/5080/5090 等 Blackwell 架构 |

### 使用流程

**1. 启动 Docker Desktop**

GPU 模式依赖 Docker 容器运行，**必须先启动 Docker Desktop** 才能使用 GPU：

- 开始菜单 → Docker Desktop
- 等待系统托盘图标变绿（约 30 秒）
- 可在 Docker Desktop 设置中勾选 `Start Docker Desktop when you sign in` 实现开机自启

**2. 运行 OCR 转换**

#### 方式一：使用便捷脚本（推荐）

将 PDF 文件放入 `input/` 目录后，直接运行：

```powershell
# 自动处理 input 文件夹下的 PDF
.\convert-input.ps1

# 指定文件名和输出名
.\convert-input.ps1 -PdfFile "你的文件.pdf" -Output "结果.md"
```

输出文件自动保存到 `output/` 目录。

#### 方式二：手动设置环境变量

```powershell
# 设置输入/输出文件名
$env:PDF_FILE="你的文件.pdf"
$env:OUTPUT_FILE="output.md"

# 启动容器进行 OCR（自动使用 GPU）
docker compose run --rm lawtomd-gpu
```

**3. 完成后**

- 容器自动退出，GPU 资源自动释放
- 输出文件保存到 `./output/` 目录
- 不使用时可关闭 Docker Desktop，不影响日常工作

### 配置说明

| 配置项 | 当前值 | 说明 |
|--------|--------|------|
| **镜像** | `paddleocr-vl:latest-nvidia-gpu-sm120` | 官方 Blackwell 专用镜像 |
| **检测模型** | `PP-OCRv4_server_det` | 高精度文字检测 |
| **识别模型** | `PP-OCRv4_server_rec` | 高精度文字识别 |
| **后端** | PaddlePaddle GPU | 自动检测 RTX 5060 |

### 模型版本对比

实测 284 页法律书籍 PDF（RTX 5060）：

| 模型 | 耗时 | 准确率 | 推荐场景 |
|------|------|--------|---------|
| **PP-OCRv4 server** | 9 分 20 秒 | ⭐⭐⭐⭐⭐ 最佳 | 准确率优先（推荐） |
| PP-OCRv5 server | 7 分 59 秒 | ⭐⭐⭐⭐ 良好 | 平衡选择 |
| PP-OCRv4 mobile | 5 分 11 秒 | ⭐⭐⭐ 一般 | 速度优先 |

### CPU 模式（备选）

如不希望启动 Docker，可使用 CPU 模式：

```powershell
$env:LAWTOMD_USE_GPU="0"
$env:PDF_FILE="你的文件.pdf"
docker compose run --rm lawtomd-gpu
```

或直接使用本地 Python 环境（不依赖 Docker）：

```bash
pip install -e ".[ocr]"
lawtomd convert 你的文件.pdf --ocr force
```

### 优势 vs 劣势

| 方面 | 说明 |
|------|------|
| ✅ 优势 | 需要 OCR 时才启动 Docker，平时 GPU 0 占用 |
| ✅ 优势 | 不污染主机 Python 环境 |
| ✅ 优势 | 避免 Blackwell 架构 PaddlePaddle 兼容性问题 |
| ⚠️ 劣势 | 每次需启动 Docker Desktop |
| ⚠️ 劣势 | 首次拉取镜像约 10GB |

详细使用说明见 [DOCKER.md](./DOCKER.md)。

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

# 查看设备性能检测
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
| `--format` | `markdown` | 输出格式: `markdown` 或 `json` |
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
# 批量转换
lawtomd batch ./pdfs/ -o ./output/

# 扁平化输出（所有 .md 在同一目录）
lawtomd batch ./pdfs/ -o ./output/ --flatten

# 批量 OCR
lawtomd batch ./pdfs/ -o ./output/ --ocr auto

# 并行处理（8 个并发）
lawtomd batch ./pdfs/ -o ./output/ --workers 8
```

### `profile` — 设备性能检测

```bash
lawtomd profile
```

检测当前设备的 CPU 核心数、内存容量、GPU 信息，输出性能等级和推荐的 OCR 方案。同时显示各 OCR 后端的安装状态。

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
                │     builder.py      │── → 完整 Markdown
                │ YAML 头 + 标题 +正文 │
                ╰─────────────────────╯
```

### 模块职责

| 模块 | 文件 | 核心职责 |
|------|------|----------|
| 数据模型 | `models.py` | LineMeta / LawMeta / JudgmentMeta / HierarchyNode / DocType 定义 |
| 模式库 | `patterns.py` | 30+ 预编译正则，覆盖编/章/节/条/当事人/裁判结果/法律引用/案号等 |
| 文本提取 | `extractor.py` | 双策略提取、页眉页脚过滤、OCR 调度、表格提取、文档类型检测 |
| 文本规范化 | `normalizer.py` | 全角空格统一、OCR 误识别修正、自定义替换规则 |
| 页眉页脚过滤 | `header_footer.py` | 标准模式 + 自定义签名过滤 |
| 元数据提取 | `metadata.py` | 法规标题、文号、日期、颁布机关等元数据提取 |
| 结构识别 | `structure.py` | 多策略解析（法规/判决书）、层级状态机、款缩进检测、子条款归并、引用提取 |
| Markdown 组装 | `builder.py` | YAML 元数据头（文档类型感知）、层级标题映射、anchor + 引用注释、JSON 输出 |
| OCR 调度器 | `ocr.py` | 统一 OcrEngine 接口，PDF 页面→图像渲染 |
| PaddleOCR 后端 | `ocr_paddle.py` | PaddleOCR 延迟初始化，GPU 自动检测，坐标转换 |
| 设备检测 | `profiler.py` | CPU/内存/GPU 检测，GPU 可用性判断 |
| 类型定义 | `types.py` | OcrBackendProtocol、OcrMode 等公共类型 |
| CLI 入口 | `main.py` | click 命令组（convert + batch + profile），支持 --format/--validate/--workers 选项 |

---

## 技术设计

### 层级识别算法

1. **文档类型检测**：根据首页文本自动判断法律法规/判决书/司法解释
2. **标题检测**：用正则判断文本行属于编/章/节/条（法规）或 当事人/诉讼记录/裁判结果/审判人员（判决书）
3. **子条款检测**：`（一）`、`1.` 等模式匹配为项/目级别，挂在当前条下
4. **树构建**：维护一个层级栈，新节点按优先级找到正确父节点
5. **目录去重**：同标题且无实质内容的节点自动合并
6. **引用提取**：遍历树节点，提取所有法律引用标注（`《XXX》第X条`）

### OCR 架构

```
                    OcrEngine (单例)
                   ┌────────────────┐
                   │ PaddleOCR      │──→ profiler.py 检测 GPU 可用性
                   │                │    ┌──────────────────────┐
                   │   GPU 可用?    │──→ │ GPU 加速模式         │
                   │                │    │                      │
                   │   仅 CPU?      │──→ │ CPU 模式             │
                   │                │    └──────────────────────┘
                   └────────────────┘
```

- **GPU 自动检测**：启动时自动检测 NVIDIA GPU，有则启用加速
- **单例模式**：全局复用，避免重复加载模型

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
│   ├── metadata.py       # 元数据提取（标题/文号/日期/机关）
│   ├── structure.py      # 结构识别引擎（款缩进检测/引用提取）
│   ├── builder.py        # Markdown/JSON 组装
│   ├── ocr.py            # OCR 引擎调度器（统一接口）
│   ├── ocr_paddle.py     # PaddleOCR 高性能后端
│   ├── profiler.py       # 设备性能检测 + GPU 可用性判断
│   └── types.py          # 公共类型定义（OcrBackendProtocol 等）
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
| `test_ocr.py` | OCR 转换、引擎初始化、PDF 提取 |
| `test_e2e.py` | 全流水线：提取→结构→Markdown |
