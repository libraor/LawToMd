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
import os
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
        return "PaddleOCR (PP-OCRv5)"

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
            # 设置环境变量 LAWTOMD_FORCE_CPU=1 可强制使用 CPU 模式
            if os.environ.get("LAWTOMD_FORCE_CPU") == "1":
                use_gpu = False
            else:
                use_gpu = self._detect_gpu_available()
            device = "gpu" if use_gpu else "cpu"

            # PaddleOCR 3.x API: PP-OCRv5_mobile
            # PP-OCRv6 模型导出有 bug (strides 属性类型错误)，暂不可用
            det_model = "PP-OCRv5_mobile_det"
            rec_model = "PP-OCRv5_mobile_rec"
            ocr_ver = "PP-OCRv5"

            # 构建引擎参数
            ocr_kwargs = dict(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
                device=device,
                ocr_version=ocr_ver,
                text_detection_model_name=det_model,
                text_recognition_model_name=rec_model,
                text_det_limit_side_len=2000,
                text_det_limit_type="max",
            )

            if use_gpu:
                # GPU 模式：优先使用 ONNX Runtime 后端
                # PaddlePaddle 3.0 不支持 Blackwell 架构 (compute capability 12.0)，
                # ONNX Runtime + CUDA 可绕过此限制
                try:
                    import onnxruntime  # noqa: F401

                    ocr_kwargs["engine"] = "onnxruntime"
                    ocr_kwargs["enable_mkldnn"] = False
                    # 配置 ONNX Runtime 使用 GPU 执行提供者
                    ocr_kwargs["engine_config"] = {
                        "providers": ["CUDAExecutionProvider", "CPUExecutionProvider"]
                    }
                    logger.info("使用 ONNX Runtime 后端 (GPU)")
                except ImportError:
                    logger.warning("onnxruntime 未安装，回退到 PaddlePaddle 后端")
            else:
                # CPU 模式：禁用 oneDNN，规避 PIR 执行器 bug
                # ConvertPirAttribute2RuntimeAttribute not support
                ocr_kwargs["enable_mkldnn"] = False

            self._ocr = PaddleOCR(**ocr_kwargs)
            self._initialized = True
            gpu_status = "GPU" if use_gpu else "CPU"
            model_tag = f"{ocr_ver}_mobile"
            logger.info("PaddleOCR 引擎初始化完成 (%s mode, %s)", gpu_status, model_tag)
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

        # PaddleOCR 3.x: 使用 predict() 替代已废弃的 ocr()
        raw = self._ocr.predict(img_input)
        if not raw:
            return []

        lines: list[LineMeta] = []

        # PaddleOCR 3.x 返回 OCRResult 对象列表
        for page_result in raw:
            dt_polys = page_result.get("dt_polys", [])
            rec_texts = page_result.get("rec_texts", [])
            rec_scores = page_result.get("rec_scores", [])

            if not dt_polys or not rec_texts:
                continue

            for bbox, text, score in zip(dt_polys, rec_texts, rec_scores):
                if not text or not text.strip():
                    continue
                if score < min_confidence:
                    logger.debug(
                        "跳过低置信度文本 '%s' (conf=%.3f)", text, score
                    )
                    continue

                # 将 numpy 数组转换为列表
                if hasattr(bbox, "tolist"):
                    bbox = bbox.tolist()
                
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
