# Changelog

所有重要变更将记录在此文件中。格式基于 [Keep a Changelog](https://keepachangelog.com/)。

## [Unreleased]

### Added
- 法律书籍电子化支持（`DocType.BOOK`）：自动检测前言/序言/后记/附录/ISBN/出版社
- 书籍结构识别：前言→章→节→小节→正文+脚注→附录/后记
- 脚注检测：基于脚注标记（①②③/[1][2]）和小字号识别
- 小节标题识别：`一、` `二、` 等中文数字+顿号格式
- 书籍元数据提取：书名、作者、出版社、ISBN、出版日期
- 书籍 Markdown 输出：脚注用 `<small>` 标签，YAML 头含 author/publisher/isbn
- `--validate` 标志：条号连续性检查，检测缺失条号
- `--format json` 选项：输出结构化 JSON 而非 Markdown
- 款（CLAUSE）层级识别：基于 x0 缩进自动检测条下款
- 前导内容保留：法规标题、颁布信息等收集到 `LawMeta.extra["preamble"]`
- 表格提取：`page.extract_tables()` 自动转为 Markdown 表格
- `cn_to_arabic` 支持"万"级别数字转换（最高九万九千九百九十九）
- 批量处理并行化：`--workers` 选项控制并发数
- 进度条显示：批量处理时自动显示 tqdm 进度（未安装时优雅降级）
- 法律引用 Markdown 链接：`《XXX》第X条` 自动转换为内部锚点链接

### Changed
- 元数据标题提取改为相对字号（max font size * 0.9），替代硬编码 `font_size >= 14`
- `_yaml_escape` 改用 `yaml.safe_dump`，消除手写转义逻辑
- 批量处理默认并行执行，提升大目录处理速度
- OCR 后端抽象为 `OcrBackendProtocol`，支持多后端插拔

### Fixed
- 目录去重：比较 `level` + `title` 而非仅 `title`，防止不同层级同名节点误合并
- `extract_pdf` 双重打开 PDF 问题，合并为单次打开
- 全局可变状态线程安全化（config 加载、OCR 引擎单例）
- 结构识别中表格行未正确处理的问题

### Refactored
- 拆分 `extractor.py` → `normalizer.py` + `header_footer.py` + `metadata.py`
- 合并 `_lines_to_nodes` / `_lines_to_judgment_nodes` 公共逻辑
- `LEVEL_ORDER` 移入 `Level` 枚举
- `_OcrMode` / `_OcrEngine` 移到公共类型模块 `src/types.py`
- 删除 `_OCR_FIXES` 硬编码，统一用 `replace.yaml` 作为单一数据源

---

## [0.1.0] - 初始版本

### Added
- 核心流水线：PDF → 文本提取 → 结构识别 → Markdown 组装
- 14 个预编译正则覆盖编/章/节/条/项/目/文号/日期
- 优先级栈建树算法 + 目录去重
- YAML 元数据头 + 层级标题 + anchor 注释
- CLI：`convert` / `batch` 命令
- OCR 支持：PaddleOCR 延迟初始化单例、分批处理、内存管理
- 多文档类型支持：法律法规、判决书、司法解释
