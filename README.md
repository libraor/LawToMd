# LawToMd

**法律 PDF → Markdown 转换工具**，面向批量化法律文档处理。

自动识别法律文档特有的 **编 → 章 → 节 → 条 → 款 → 项 → 目** 层级结构，输出结构化 Markdown。

---

## 适用场景

- **法律知识库构建** — 批量处理整套法规体系，生成结构化文档
- **法条对比分析** — 新旧法规条文级别的差异比对
- **LLM 微调数据准备** — 清洗、结构化后的高质量法律语料

---

## 功能

- 📄 **PDF 文本提取** — 基于 pdfplumber，保留坐标、字号、加粗等信息，过滤页眉页脚
- 🏛 **层级结构识别** — 自动解析编/章/节/条/款/项/目，构建层级树
- 📝 **结构化 Markdown** — YAML 元数据头 + 层级标题 + anchor 注释
- ⚡ **批量处理** — 递归扫描目录，保持子目录结构或扁平化输出
- 🔧 **可配置** — 页眉页脚过滤、目录生成、anchor 注释均可调

---

## 安装

```bash
# 从源码安装
git clone https://github.com/YOUR_ORG/lawtomd.git
cd lawtomd
pip install -e .

# 确认安装
lawtomd --help
```

**依赖**：`pdfplumber` (PDF 解析引擎)、`click` (CLI 框架)。

---

## 快速开始

```bash
# 单文件转换
lawtomd convert 民法典.pdf

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

```markdown
---
title: 中华人民共和国民法典
doc_id: 中华人民共和国主席令第四十五号
publish_date: 2020年5月28日
effective_date: 2021年1月1日
authority: 全国人民代表大会
source: 民法典.pdf
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

---

## 架构

```
                ╭─────────────────────╮
PDF 文件 ─────→│    extractor.py     │── → LineMeta[]
                │ pdfplumber 文本+坐标  │
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
| 数据模型 | `models.py` | LineMeta / LawMeta / HierarchyNode 定义 |
| 模式库 | `patterns.py` | 14 个预编译正则，覆盖编、章、节、条、项、目、文号、日期 |
| 文本提取 | `extractor.py` | 双策略提取（extract_text_lines / words 聚类），页眉页脚过滤 |
| 结构识别 | `structure.py` | 层级状态机、子条款归并、目录去重、路径构建 |
| Markdown 组装 | `builder.py` | YAML 元数据头、层级标题映射、anchor 注释 |
| CLI 入口 | `main.py` | click 命令组（convert + batch） |

---

## 技术设计

### 层级识别算法

1. **标题检测**：用正则判断文本行属于编 / 章 / 节 / 条
2. **子条款检测**：`（一）`、`1.` 等模式匹配为项/目级别，挂在当前条下
3. **树构建**：维护一个层级栈，新节点按优先级找到正确父节点
4. **目录去重**：同标题且无实质内容的节点自动合并

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
│   ├── extractor.py      # PDF 文本提取
│   ├── structure.py      # 结构识别引擎
│   └── builder.py        # Markdown 组装
├── config/
│   └── replace.yaml      # 常用词替换规则
├── tests/
│   ├── conftest.py       # 测试夹具
│   ├── test_patterns.py  # 模式测试
│   ├── test_structure.py # 结构测试
│   ├── test_builder.py   # 构建测试
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
| `test_patterns.py` | 16 | 各级别正则匹配/不匹配 |
| `test_structure.py` | 5 | 空输入、单条、多级、子条款、收集 |
| `test_builder.py` | 4 | 基础构建、多级、单条、无 anchor |
| `test_e2e.py` | 1 | 全流水线：提取→结构→Markdown |
