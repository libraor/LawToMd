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

## 计划中

### P0 — 稳定性

- [ ] 增加 extractor 单元测试（页眉页脚过滤、跨页去重、元数据提取）
- [ ] 增加 OCR 模式集成测试（mock PaddleOCR）
- [ ] 处理 pdfplumber 非标准编码 PDF 的异常

### P1 — 功能增强

- [ ] 启用 `config/replace.yaml`：常用词/标点规范化替换
- [ ] 条号中文→阿拉伯数字转换（anchor ID 可读性）
- [ ] 支持 `--format json` 输出结构化 JSON
- [ ] 并行处理：多线程/多进程批量转换

### P2 — 体验优化

- [ ] 进度条（tqdm）显示批量处理进度
- [ ] 生成 Markdown 目录时添加页码链接
- [ ] 支持自定义层级→标题映射配置
- [ ] 条文修订标注（新旧法对比模式）

---

## 架构约束

- 所有 OCR/PyMuPDF/OpenCV 导入必须延迟，不影响无 OCR 依赖时的核心功能
- `OcrEngine` 保持线程安全单例设计
- 测试不依赖外部服务，纯内存操作
- `src/` 是包目录，import 路径为 `src.models`、`src.patterns` 等
