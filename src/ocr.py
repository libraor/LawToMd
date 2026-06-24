"""OCR 引擎调度器。

使用第三方 OCR API 作为 OCR 后端。

公共 API：
    from src.ocr import OcrEngine, pdf_page_to_image, page_has_text, is_available

    engine = OcrEngine.get_instance()
    lines = engine.ocr_page(image, page_num=1, dpi=300)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from threading import Lock
from typing import Optional

from src.models import LineMeta

logger = logging.getLogger(__name__)

_engine_lock = Lock()

# 判定页面有文字的最少字符数
_MIN_CHARS_FOR_TEXT = 10

# 渲染图片长边最大像素数，防止大尺寸页面 OOM
_MAX_IMAGE_PIXELS = 4000


# ── 公共辅助 ──────────────────────────────────────────────


def is_available() -> bool:
    """检查 OCR API 是否可用（不触发初始化）。"""
    from src.ocr_api import is_api_available

    return is_api_available()


def page_has_text(page) -> bool:
    """判断 pdfplumber Page 是否包含可提取文字。"""
    chars = getattr(page, "chars", None) or []
    return len(chars) >= _MIN_CHARS_FOR_TEXT


# ── OcrEngine ─────────────────────────────────────────────


class OcrEngine:
    """OCR API 引擎单例封装。

    延迟初始化，首次调用 get_instance() 时加载配置。
    """

    _instance: Optional["OcrEngine"] = None

    def __init__(self) -> None:
        self._backend = None

        from src.ocr_api import ApiOcrBackend

        self._backend = ApiOcrBackend()
        logger.info("OCR 引擎初始化: 第三方 OCR API")

    @classmethod
    def get_instance(cls) -> "OcrEngine":
        """获取或创建 OcrEngine 单例（线程安全）。"""
        if cls._instance is None:
            with _engine_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例（仅用于测试或批量处理间释放内存）。"""
        with _engine_lock:
            if cls._instance is not None and cls._instance._backend is not None:
                cls._instance._backend.release()
            cls._instance = None

    def ocr_page(
        self,
        image,
        page_num: int,
        min_confidence: float = 0.5,
        dpi: int = 300,
    ) -> list[LineMeta]:
        """对单张 PIL Image 执行 OCR，返回 LineMeta 列表。

        Parameters
        ----------
        image : PIL.Image
            页面图像。
        page_num : int
            页码（从 1 开始）。
        min_confidence : float
            最低置信度阈值。
        dpi : int
            渲染图像时使用的 DPI，用于坐标转换。

        Returns
        -------
        list[LineMeta]
            按 (y0, x0) 排序的文本行。
        """
        return self._backend.ocr_page(image, page_num, min_confidence, dpi)

    @property
    def backend_name(self) -> str:
        return "api"

    @property
    def backend_display_name(self) -> str:
        return getattr(self._backend, "display_name", "OCR API")

    @property
    def profile(self) -> None:
        """设备性能档案（API 后端不可用）。"""
        return None


# ── PDF 页面 → 图像 ──────────────────────────────────────


def pdf_page_to_image(
    pdf_path: str | Path,
    page_index: int,
    dpi: int = 300,
    max_pixels: int = _MAX_IMAGE_PIXELS,
):
    """将 PDF 单页渲染为 PIL Image。

    Parameters
    ----------
    pdf_path : str or Path
        PDF 文件路径。
    page_index : int
        从 0 开始的页面索引（= page_num - 1）。
    dpi : int
        目标渲染分辨率（默认 300）。
    max_pixels : int
        长边最大像素数，超出自动等比缩放。

    Returns
    -------
    (PIL.Image.Image, int)
        (RGB 页面图像, 有效 DPI)，有效 DPI 用于后续坐标转换。
    """
    import fitz  # PyMuPDF

    pdf_path = Path(pdf_path)
    doc = fitz.open(str(pdf_path))
    try:
        page = doc.load_page(page_index)
        rect = page.rect
        page_w = rect.width   # pt
        page_h = rect.height  # pt

        # 限制长边像素数，调整渲染 DPI
        scale = dpi / 72.0
        raw_w = int(page_w * scale)
        raw_h = int(page_h * scale)
        long_side = max(raw_w, raw_h)
        if long_side > max_pixels:
            scale *= max_pixels / long_side
            effective_dpi = int(72 * scale)
            logger.debug(
                "Page %d: limiting image %dx%d → %dx%d (dpi %d → %d)",
                page_index + 1,
                raw_w, raw_h,
                int(page_w * scale), int(page_h * scale),
                dpi, effective_dpi,
            )
        else:
            effective_dpi = dpi

        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        from PIL import Image

        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        # 显式释放 pixmap 内存
        pix = None
        return img, effective_dpi
    finally:
        doc.close()
