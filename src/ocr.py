"""PaddleOCR 封装引擎。

提供延迟初始化单例、PDF 页→图像转换、OCR 结果→LineMeta 转换。
所有 PaddleOCR / PyMuPDF / OpenCV 导入均为延迟的，无 OCR 依赖时不影响原有功能。

用法:
    from src.ocr import OcrEngine, pdf_page_to_image, is_available

    if is_available():
        engine = OcrEngine.get_instance()
        image, dpi = pdf_page_to_image("民法典.pdf", page_index=0)
        lines = engine.ocr_page(image, page_num=1, dpi=dpi)
"""

from __future__ import annotations

import logging
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
    """检查 PaddleOCR 依赖是否可导入（不触发初始化）。"""
    try:
        _ensure_torch_dll_path()
        import paddleocr  # noqa: F401
        from paddleocr import PaddleOCR  # noqa: F401

        return True
    except Exception:
        return False


def _ensure_torch_dll_path() -> None:
    """Windows 环境下确保 torch DLL 可被找到。

    PaddleOCR 依赖 albumentations，后者在导入时触发 torch 加载。
    torch 的 _load_dll_libraries 需要正确的 DLL 搜索路径，
    在某些 Windows 环境下需要预先加载 torch 以设置路径。
    """
    import sys

    if sys.platform == "win32":
        try:
            import torch  # noqa: F401
        except Exception:
            pass


def page_has_text(page) -> bool:
    """判断 pdfplumber Page 是否包含可提取文字。"""
    chars = getattr(page, "chars", None) or []
    return len(chars) >= _MIN_CHARS_FOR_TEXT


# ── OcrEngine 单例 ────────────────────────────────────────


class OcrEngine:
    """PaddleOCR 延迟初始化单例。

    首次调用 get_instance() 时才加载 PaddleOCR 模型，
    后续调用复用同一实例。
    """

    _instance: Optional["OcrEngine"] = None
    _initialized: bool = False

    def __init__(self) -> None:
        self._ocr = None

    @classmethod
    def get_instance(cls) -> "OcrEngine":
        """获取或创建 OcrEngine 单例（线程安全）。"""
        if cls._instance is None:
            with _engine_lock:
                if cls._instance is None:
                    inst = cls()
                    inst._initialize()
                    cls._instance = inst
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例（仅用于测试）。"""
        with _engine_lock:
            cls._instance = None
            cls._initialized = False

    def _initialize(self) -> None:
        """延迟导入 PaddleOCR 并初始化引擎。"""
        if self._initialized:
            return
        try:
            import os

            # 单线程运行，减少内存占用
            os.environ.setdefault("OMP_NUM_THREADS", "1")
            os.environ.setdefault("MKL_NUM_THREADS", "1")

            _ensure_torch_dll_path()
            from paddleocr import PaddleOCR

            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang="ch",
                show_log=False,
                use_gpu=False,
                cpu_threads=1,
            )
            self._initialized = True
            logger.info("PaddleOCR 引擎初始化完成 (CPU mode, single-thread)")
        except ImportError as e:
            raise ImportError(
                "PaddleOCR 依赖未安装。请运行: pip install 'lawtomd[ocr]'"
            ) from e

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
            最低置信度阈值，低于此值的识别结果被丢弃。
        dpi : int
            渲染图像时使用的 DPI，用于坐标缩放回 PDF 点空间。

        Returns
        -------
        list[LineMeta]
            按 (y0, x0) 排序的文本行。
        """
        if self._ocr is None:
            raise RuntimeError("OcrEngine 未初始化")

        # PaddleOCR 需要 numpy 数组或文件路径
        import numpy as np

        if hasattr(image, "save"):
            # PIL Image → numpy array
            img_input = np.array(image)
        else:
            img_input = image

        raw = self._ocr.ocr(img_input, cls=True)
        if not raw or not raw[0]:
            return []

        results = raw[0]
        lines: list[LineMeta] = []

        for item in results:
            bbox, info = item
            text, confidence = info
            if not text or not text.strip():
                continue
            if confidence < min_confidence:
                logger.debug(
                    "跳过低置信度文本 '%s' (conf=%.3f)", text, confidence
                )
                continue

            line = _paddle_bbox_to_linemeta(bbox, text, page_num, dpi=dpi)
            lines.append(line)

        lines.sort(key=lambda l: (l.y0, l.x0))
        return lines


# ── 坐标转换 ──────────────────────────────────────────────


def _paddle_bbox_to_linemeta(
    bbox: list[list[float]],
    text: str,
    page_num: int,
    dpi: int = 300,
) -> LineMeta:
    """将 PaddleOCR 的 bbox 转换为 LineMeta。

    PaddleOCR bbox 格式: [[x0,y0], [x1,y0], [x1,y1], [x0,y1]]
    坐标单位为像素，需缩放回 PDF 点空间 (72 DPI)。
    """
    scale = 72.0 / dpi
    xs = [p[0] * scale for p in bbox]
    ys = [p[1] * scale for p in bbox]
    x0 = min(xs)
    y0 = min(ys)
    x1 = max(xs)
    y1 = max(ys)
    height = y1 - y0

    return LineMeta(
        text=text.strip(),
        page_num=page_num,
        x0=round(x0, 1),
        y0=round(y0, 1),
        x1=round(x1, 1),
        y1=round(y1, 1),
        font_size=round(height, 1),
        bold=False,
        fontname="",
    )


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

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        # 显式释放 pixmap 内存
        pix = None
        return img, effective_dpi
    finally:
        doc.close()
