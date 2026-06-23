#!/bin/bash
# 安装额外依赖
pip install pdfplumber pyyaml PyMuPDF -q

# 运行 OCR 转换
python3 -m src.main convert "$INPUT_FILE" --ocr force -o "$OUTPUT_FILE"
