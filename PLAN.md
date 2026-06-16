# LawToMd 开发计划

## 项目状态

核心流水线已可用：PDF → 文本提取 → 结构识别 → Markdown 组装。OCR 支持已集成。

---

## 已完成

- [x] 核心流水线：extractor → structure → builder
- [x] 14 个预编译正则覆盖编/章/节/条/项/目/文号/日期
- [x] 优先级栈建树算法 + 目录去重
- [x] YAML 元数据头 + 层级标题 + anchor 注释
- [x] CLI：convert / batch 命令
- [x] OCR 支持：PaddleOCR 延迟初始化单例、分批处理、内存管理
- [x] 代码清理：移除未使用函数、修复资源泄漏、整理导入

---

## Phase 1 — 稳定性修复（P0）

- [x] 1. 修复目录去重：比较 `level` + `title` 而非仅 `title`，防止不同层级同名节点误合并
- [x] 2. 修复 `extract_pdf` 双重打开 PDF，合并为单次打开
- [x] 3. 将 `_OcrMode`/`_OcrEngine` 移到公共类型模块（`src/types.py`）
- [x] 4. 补充 `cn_to_arabic`、`detect_doc_type`、`extract_law_references` 单元测试
- [x] 5. 补充 `normalize_text`、`_filter_lines`、元数据提取单元测试
- [x] 6. E2E 测试重构为 pytest 标准格式

## Phase 2 — 架构重构（P1）

- [x] 7. 拆分 `extractor.py` → `normalizer.py` + `header_footer.py` + `metadata.py`
- [x] 8. 删除 `_OCR_FIXES` 硬编码，统一用 `replace.yaml` 作为单一数据源
- [x] 9. OCR 后端 ABC 抽象（`OcrBackendProtocol`）
- [x] 10. 合并 `_lines_to_nodes` / `_lines_to_judgment_nodes` 公共逻辑
- [x] 11. `LEVEL_ORDER` 移入 `Level` 枚举，消除独立字典
- [x] 12. 全局可变状态线程安全化（`lru_cache` 或 `Lock`）

## Phase 3 — 功能增强（P2）

- [x] 13. 款（CLAUSE）层级识别：基于 x0 缩进检测
- [x] 14. 前导内容保留：收集到 `LawMeta.extra["preamble"]`
- [x] 15. 元数据标题提取改为相对字号，替代 `font_size >= 14` 硬编码
- [x] 16. 法律引用生成 Markdown 链接，替代 HTML 注释
- [x] 17. `--format json` 输出结构化 JSON
- [x] 18. 表格提取：`page.extract_tables()` → Markdown 表格

## Phase 4 — 体验优化（P3）

- [x] 19. 批量处理并行化（`ProcessPoolExecutor`）
- [x] 20. 进度条（tqdm）显示批量处理进度
- [x] 21. `--validate` 校验模式：条号连续性检查
- [x] 22. `cn_to_arabic` 支持"万"级别
- [x] 23. `_yaml_escape` 改用 `yaml.safe_dump`，消除手写转义

---

## 架构约束

- 所有 OCR/PyMuPDF/OpenCV 导入必须延迟，不影响无 OCR 依赖时的核心功能
- `OcrEngine` 保持线程安全单例设计
- 测试不依赖外部服务，纯内存操作
- `src/` 是包目录，import 路径为 `src.models`、`src.patterns` 等
