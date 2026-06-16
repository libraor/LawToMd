"""OCR 引擎调度器。

根据设备性能自动选择 OCR 后端（PaddleOCR 高性能 或 RapidOCR 轻量版），
也支持用户手动指定。提供统一的 OcrEngine 接口，对上层调用者透明。

公共 API 保持向后兼容：
    from src.ocr import OcrEngine, pdf_page_to_image, page_has_text, is_available

    engine = OcrEngine.get_instance()           # 自动选择后端
    engine = OcrEngine.get_instance(backend="paddle")  # 强制 PaddleOCR
    engine = OcrEngine.get_instance(backend="lite")    # 强制轻量版
    lines = engine.ocr_page(image, page_num=1, dpi=300)
"""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock
from typing import Optional

from src.models import LineMeta
from src.profiler import DeviceProfile, detect_device_profile, recommend_ocr_backend
from src.types import OcrBackendProtocol

logger = logging.getLogger(__name__)

_engine_lock = Lock()

# 判定页面有文字的最少字符数
_MIN_CHARS_FOR_TEXT = 10

# 渲染图片长边最大像素数，防止大尺寸页面 OOM
_MAX_IMAGE_PIXELS = 4000


# ── 公共辅助 ──────────────────────────────────────────────


def is_available() -> bool:
    """检查是否有任何 OCR 后端可用（不触发初始化）。"""
    from src.ocr_paddle import is_paddle_available
    from src.ocr_lite import is_lite_available

    return is_paddle_available() or is_lite_available()


def is_paddle_available() -> bool:
    """检查 PaddleOCR 后端是否可用。"""
    from src.ocr_paddle import is_paddle_available as _check

    return _check()


def is_lite_available() -> bool:
    """检查 RapidOCR 轻量版后端是否可用。"""
    from src.ocr_lite import is_lite_available as _check

    return _check()


def page_has_text(page) -> bool:
    """判断 pdfplumber Page 是否包含可提取文字。"""
    chars = getattr(page, "chars", None) or []
    return len(chars) >= _MIN_CHARS_FOR_TEXT


# ── OcrEngine 调度器 ──────────────────────────────────────


class OcrEngine:
    """OCR 引擎调度器，根据设备性能自动选择后端。

    支持三种后端选择模式：
    - "auto"   → 根据设备性能自动推荐（默认）
    - "paddle" → 强制使用 PaddleOCR 高性能后端
    - "lite"   → 强制使用 RapidOCR 轻量版后端

    当 backend="auto" 时，会检测设备性能并选择推荐的后端。
    如果推荐的后端不可用，会自动回退到另一个可用后端。
    """

    _instance: Optional["OcrEngine"] = None
    _backend_choice: str = "auto"

    def __init__(self, backend: str = "auto") -> None:
        self._backend_name: str = ""
        self._backend: OcrBackendProtocol | None = None
        self._profile: Optional[DeviceProfile] = None

        # 解析后端选择
        if backend == "auto":
            self._profile = detect_device_profile()
            recommended = recommend_ocr_backend(self._profile)
            self._backend_name = self._resolve_backend(recommended)
        else:
            self._backend_name = self._resolve_backend(backend)

        # 创建后端实例
        self._backend = self._create_backend(self._backend_name)

        logger.info(
            "OCR 后端选择: %s%s",
            self._backend_name,
            f" (自动推荐: 设备性能={self._profile.tier.value})" if self._profile else "",
        )

    @classmethod
    def get_instance(cls, backend: str = "auto") -> "OcrEngine":
        """获取或创建 OcrEngine 单例（线程安全）。

        Parameters
        ----------
        backend : str
            后端选择: "auto" | "paddle" | "lite"
        """
        # 记住用户的选择，reset 后仍使用同一后端
        if backend != "auto":
            cls._backend_choice = backend

        if cls._instance is not None and backend != "auto" and backend != cls._instance._backend_name:
            # backend 参数变化，需要重建实例
            logger.info("OCR 后端切换: %s → %s，重建实例", cls._instance._backend_name, backend)
            cls.reset()

        if cls._instance is None:
            with _engine_lock:
                if cls._instance is None:
                    effective_backend = cls._backend_choice
                    cls._instance = cls(backend=effective_backend)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例（仅用于测试或批量处理间释放内存）。"""
        with _engine_lock:
            if cls._instance is not None and cls._instance._backend is not None:
                cls._instance._backend.release()
            cls._instance = None

    def _resolve_backend(self, preferred: str) -> str:
        """解析后端选择，如果首选不可用则回退。

        Parameters
        ----------
        preferred : str
            首选后端: "paddle" 或 "lite"

        Returns
        -------
        str
            实际可用的后端名称。
        """
        # 先检查首选后端，避免同时加载两个后端导致内存不足
        if preferred == "paddle":
            from src.ocr_paddle import is_paddle_available
            if is_paddle_available():
                return "paddle"
            # 回退到 lite
            from src.ocr_lite import is_lite_available
            if is_lite_available():
                logger.info("PaddleOCR 不可用，回退到 RapidOCR")
                return "lite"
        else:
            from src.ocr_lite import is_lite_available
            if is_lite_available():
                return "lite"
            # 回退到 paddle
            from src.ocr_paddle import is_paddle_available
            if is_paddle_available():
                logger.info("RapidOCR 不可用，回退到 PaddleOCR")
                return "paddle"

        # 都不可用
        raise ImportError(
            "无可用的 OCR 后端。请安装至少一种:\n"
            "  pip install 'lawtomd[ocr]'      # PaddleOCR 高性能版\n"
            "  pip install 'lawtomd[ocr-lite]'  # RapidOCR 轻量版"
        )

    def _create_backend(self, name: str) -> OcrBackendProtocol:
        """创建后端实例。"""
        if name == "paddle":
            from src.ocr_paddle import PaddleOcrBackend

            return PaddleOcrBackend()
        elif name == "lite":
            from src.ocr_lite import LiteOcrBackend

            return LiteOcrBackend()
        else:
            raise ValueError(f"未知 OCR 后端: {name}")

    def ocr_page(
        self,
        image,
        page_num: int,
        min_confidence: float = 0.5,
        dpi: int = 300,
    ) -> list[LineMeta]:
        """对单张 PIL Image 执行 OCR，返回 LineMeta 列表。

        委托给当前后端执行实际 OCR 操作。

        Parameters
        ----------
        image : PIL.Image
            页面图像。
        page_num : int
            页码（从 1 开始）。
        min_confidence : float
            最低置信度阈值。
        dpi : int
            渲染图像时使用的 DPI，用于坐标缩放。

        Returns
        -------
        list[LineMeta]
            按 (y0, x0) 排序的文本行。
        """
        return self._backend.ocr_page(image, page_num, min_confidence, dpi)

    @property
    def backend_name(self) -> str:
        """当前使用的后端名称。"""
        return self._backend_name

    @property
    def backend_display_name(self) -> str:
        """当前后端的显示名称。"""
        if self._backend is not None:
            return self._backend.display_name
        return self._backend_name

    @property
    def profile(self) -> Optional[DeviceProfile]:
        """设备性能档案（仅 backend="auto" 时有值）。"""
        return self._profile


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
