"""PaddleOCR 高性能后端。

从 ocr.py 中提取的 PaddleOCR 引擎封装，提供延迟初始化、
GPU 自动检测和 OCR 结果→LineMeta 转换。

用法:
    from src.ocr_paddle import PaddleOcrBackend, is_paddle_available

    if is_paddle_available():
        backend = PaddleOcrBackend()
        lines = backend.ocr_page(image, page_num=1, dpi=300)
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from src.models import LineMeta

logger = logging.getLogger(__name__)


# ── 依赖检测 ──────────────────────────────────────────────


def is_paddle_available() -> bool:
    """检查 PaddleOCR 依赖是否可导入（不触发初始化）。"""
    try:
        _ensure_torch_dll_path()
        import paddleocr  # noqa: F401
        from paddleocr import PaddleOCR  # noqa: F401

        return True
    except Exception:
        return False


def _ensure_torch_dll_path() -> None:
    """Windows 环境下确保 torch DLL 可被找到。"""
    import sys

    if sys.platform == "win32":
        try:
            import torch  # noqa: F401
        except Exception:
            pass


# ── PaddleOCR 后端 ────────────────────────────────────────


class PaddleOcrBackend:
    """PaddleOCR 高性能后端。

    延迟初始化，首次调用 ocr_page() 时才加载模型。
    自动检测 GPU 可用性，有 GPU 时启用 GPU 加速。
    """

    def __init__(self) -> None:
        self._ocr = None
        self._initialized = False

    @property
    def name(self) -> str:
        return "paddle"

    @property
    def display_name(self) -> str:
        return "PaddleOCR (高性能)"

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

            # 检测 GPU 可用性
            use_gpu = self._detect_gpu_available()

            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang="ch",
                show_log=False,
                use_gpu=use_gpu,
                cpu_threads=1 if not use_gpu else 0,
            )
            self._initialized = True
            gpu_status = "GPU" if use_gpu else "CPU"
            logger.info("PaddleOCR 引擎初始化完成 (%s mode)", gpu_status)
        except ImportError as e:
            raise ImportError(
                "PaddleOCR 依赖未安装。请运行: pip install 'lawtomd[ocr]'"
            ) from e

    def _detect_gpu_available(self) -> bool:
        """检测 PaddlePaddle 是否可使用 GPU。"""
        try:
            import paddle

            return paddle.device.is_compiled_with_cuda() and paddle.device.get_device().startswith("gpu")
        except Exception:
            return False

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
            渲染图像时使用的 DPI，用于坐标缩放。

        Returns
        -------
        list[LineMeta]
            按 (y0, x0) 排序的文本行。
        """
        if not self._initialized:
            self._initialize()

        if self._ocr is None:
            raise RuntimeError("PaddleOCR 后端未初始化")

        import numpy as np

        if hasattr(image, "save"):
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

        lines.sort(key=lambda line: (line.y0, line.x0))
        return lines

    def release(self) -> None:
        """释放引擎资源。"""
        self._ocr = None
        self._initialized = False


# ── 坐标转换 ──────────────────────────────────────────────


def _paddle_bbox_to_linemeta(
    bbox: Sequence[Sequence[float | int]],
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
