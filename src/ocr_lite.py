"""轻量级 OCR 后端（基于 RapidOCR）。

使用 RapidOCR (ONNX Runtime) 替代 EasyOCR/PaddleOCR，无需 PyTorch/PaddlePaddle，
模型体积小（~20MB），CPU 推理线程可控，适合低性能设备。

用法:
    from src.ocr_lite import LiteOcrBackend, is_lite_available

    if is_lite_available():
        backend = LiteOcrBackend()
        lines = backend.ocr_page(image, page_num=1, dpi=300)
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from src.models import LineMeta

logger = logging.getLogger(__name__)


# ── 依赖检测 ──────────────────────────────────────────────


def is_lite_available() -> bool:
    """检查 RapidOCR 依赖是否可导入（不触发初始化）。"""
    try:
        from rapidocr_onnxruntime import RapidOCR  # noqa: F401

        return True
    except Exception:
        return False


# ── 轻量级 OCR 后端 ──────────────────────────────────────


class LiteOcrBackend:
    """RapidOCR 轻量级后端。

    基于 ONNX Runtime 推理，无需 PyTorch/PaddlePaddle，内存占用极低。
    延迟初始化，首次调用 ocr_page() 时才加载模型。
    自动检测 GPU 可用性，无 GPU 时使用 CPU 模式。
    """

    def __init__(self) -> None:
        self._engine = None
        self._initialized = False

    @property
    def name(self) -> str:
        return "lite"

    @property
    def display_name(self) -> str:
        return "RapidOCR (轻量版)"

    def _detect_gpu_available(self) -> bool:
        """检测 ONNX Runtime 是否可使用 GPU。"""
        try:
            import onnxruntime as ort

            providers = ort.get_available_providers()
            return "CUDAExecutionProvider" in providers or "DmlExecutionProvider" in providers
        except Exception:
            return False

    def _initialize(self) -> None:
        """延迟导入 RapidOCR 并初始化引擎。"""
        if self._initialized:
            return
        try:
            from rapidocr_onnxruntime import RapidOCR

            use_gpu = self._detect_gpu_available()

            if use_gpu:
                self._engine = RapidOCR(
                    text_score=0.5,
                    use_cuda=True,
                )
            else:
                self._engine = RapidOCR(
                    text_score=0.5,
                )

            self._initialized = True
            gpu_status = "GPU" if use_gpu else "CPU"
            logger.info("RapidOCR 引擎初始化完成 (轻量模式, %s)", gpu_status)
        except ImportError as e:
            raise ImportError(
                "RapidOCR 依赖未安装。请运行: pip install 'lawtomd[ocr-lite]'"
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

        if self._engine is None:
            raise RuntimeError("RapidOCR 后端未初始化")

        import numpy as np

        if hasattr(image, "save"):
            img_input = np.array(image)
        else:
            img_input = image

        result, _ = self._engine(img_input)

        if not result:
            return []

        lines: list[LineMeta] = []
        for item in result:
            bbox, text, confidence = item
            if not text or not text.strip():
                continue
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence < min_confidence:
                logger.debug(
                    "跳过低置信度文本 '%s' (conf=%.3f)", text, confidence
                )
                continue

            line = _rapidocr_bbox_to_linemeta(bbox, text, page_num, dpi=dpi)
            lines.append(line)

        lines.sort(key=lambda line: (line.y0, line.x0))
        return lines

    def release(self) -> None:
        """释放引擎资源。"""
        self._engine = None
        self._initialized = False


# ── 坐标转换 ──────────────────────────────────────────────


def _rapidocr_bbox_to_linemeta(
    bbox: Sequence[Sequence[float | int]],
    text: str,
    page_num: int,
    dpi: int = 300,
) -> LineMeta:
    """将 RapidOCR 的 bbox 转换为 LineMeta。

    RapidOCR bbox 格式: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
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
