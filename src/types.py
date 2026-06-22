"""LawToMd 公共类型定义。

将跨模块共享的类型别名集中定义，避免导入私有符号。
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from src.models import LineMeta

# OCR 模式：auto=对无文字页面回退, force=强制所有页面, off=禁用
OcrMode = Literal["auto", "force", "off"]


@runtime_checkable
class OcrBackendProtocol(Protocol):
    """OCR 后端必须实现的协议接口。

    所有 OCR 后端必须实现此协议，
    以确保 OcrEngine 调度器可以统一调用。
    """

    @property
    def name(self) -> str:
        """后端标识名（如 'paddle'）。"""
        ...

    @property
    def display_name(self) -> str:
        """后端显示名（如 'PaddleOCR (高性能)'）。"""
        ...

    def ocr_page(
        self,
        image,
        page_num: int,
        min_confidence: float = 0.5,
        dpi: int = 300,
    ) -> list[LineMeta]:
        """对单张 PIL Image 执行 OCR，返回 LineMeta 列表。"""
        ...

    def release(self) -> None:
        """释放引擎资源。"""
        ...
