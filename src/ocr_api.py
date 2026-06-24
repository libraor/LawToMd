"""第三方 OCR API 后端。

通过 HTTP API 调用第三方 OCR 服务（如百度、阿里云、腾讯云等）。

用法:
    from src.ocr_api import ApiOcrBackend, is_api_available

    backend = ApiOcrBackend(api_url="https://api.example.com/ocr", api_key="xxx")
    lines = backend.ocr_page(image, page_num=1, dpi=300)
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Optional

import yaml

from src.models import LineMeta

logger = logging.getLogger(__name__)

# 默认配置文件路径
_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "ocr_api.yaml"


# ── 依赖检测 ──────────────────────────────────────────────


def is_api_available() -> bool:
    """检查 HTTP 客户端依赖是否可导入。"""
    try:
        import requests  # noqa: F401
        return True
    except ImportError:
        return False


# ── 配置加载 ──────────────────────────────────────────────


def load_api_config(config_path: Optional[str | Path] = None) -> dict[str, Any]:
    """加载 OCR API 配置文件。

    配置文件格式 (YAML):
        api_url: "https://api.example.com/ocr"
        api_key: "your-api-key"
        provider: "baidu"  # baidu/aliyun/tencent/custom
        timeout: 30
        retry: 3
        headers:
            Content-Type: "application/json"
        request_template:
            image_field: "image"
            options:
                language: "zh-CN"
        response_parser:
            text_field: "words_result"
            bbox_field: "location"
            confidence_field: "confidence"
    """
    config_file = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        logger.info("加载 OCR API 配置: %s", config_file)
        return config
    return {}


# ── API 后端 ─────────────────────────────────────────────


class ApiOcrBackend:
    """第三方 OCR API 后端。

    通过 HTTP 请求调用第三方 OCR 服务，支持多种提供商。
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        provider: str = "custom",
        config_path: Optional[str | Path] = None,
    ) -> None:
        self._config = load_api_config(config_path)
        self._api_url = api_url or self._config.get("api_url", "")
        self._api_key = api_key or self._config.get("api_key", "")
        self._provider = provider or self._config.get("provider", "custom")
        self._timeout = self._config.get("timeout", 30)
        self._retry = self._config.get("retry", 3)
        self._initialized = bool(self._api_url)

    @property
    def name(self) -> str:
        return "api"

    @property
    def display_name(self) -> str:
        return f"OCR API ({self._provider})"

    def _build_request(self, image_data: bytes) -> dict[str, Any]:
        """构建 API 请求体。"""
        import base64

        template = self._config.get("request_template", {})
        image_field = template.get("image_field", "image")
        options = template.get("options", {})

        # 默认请求格式
        body = {
            image_field: base64.b64encode(image_data).decode("utf-8"),
            **options,
        }

        # 提供商特定格式
        if self._provider == "baidu":
            body = {"image": base64.b64encode(image_data).decode("utf-8")}
        elif self._provider == "aliyun":
            body = {"img": base64.b64encode(image_data).decode("utf-8")}
        elif self._provider == "tencent":
            body = {"ImageBase64": base64.b64encode(image_data).decode("utf-8")}

        return body

    def _build_headers(self) -> dict[str, str]:
        """构建 API 请求头。"""
        headers = self._config.get("headers", {})
        if self._api_key:
            if self._provider == "baidu":
                headers["Authorization"] = f"Bearer {self._api_key}"
            elif self._provider == "aliyun":
                headers["Authorization"] = f"Bearer {self._api_key}"
            elif self._provider == "tencent":
                headers["Authorization"] = self._api_key
            else:
                headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _parse_response(self, response_data: dict) -> list[tuple[list, str, float]]:
        """解析 API 响应，返回 [(bbox, text, confidence), ...]。

        不同提供商的响应格式不同，这里提供通用解析器。
        """
        parser = self._config.get("response_parser", {})
        text_field = parser.get("text_field", "text")
        bbox_field = parser.get("bbox_field", "bbox")
        confidence_field = parser.get("confidence_field", "confidence")

        results = []

        # 提供商特定解析
        if self._provider == "baidu":
            # 百度 OCR 响应格式
            words_result = response_data.get("words_result", [])
            for item in words_result:
                text = item.get("words", "")
                location = item.get("location", {})
                bbox = [
                    [location.get("left", 0), location.get("top", 0)],
                    [location.get("left", 0) + location.get("width", 0), location.get("top", 0)],
                    [location.get("left", 0) + location.get("width", 0), location.get("top", 0) + location.get("height", 0)],
                    [location.get("left", 0), location.get("top", 0) + location.get("height", 0)],
                ]
                confidence = item.get("confidence", 1.0)
                if text.strip():
                    results.append((bbox, text, confidence))

        elif self._provider == "aliyun":
            # 阿里云 OCR 响应格式
            data = response_data.get("data", {})
            content = data.get("content", [])
            for item in content:
                text = item.get("text", "")
                bbox = item.get("pos", [[0, 0], [0, 0], [0, 0], [0, 0]])
                confidence = item.get("score", 1.0)
                if text.strip():
                    results.append((bbox, text, confidence))

        elif self._provider == "tencent":
            # 腾讯云 OCR 响应格式
            text_detections = response_data.get("TextDetections", [])
            for item in text_detections:
                text = item.get("DetectedText", "")
                polygon = item.get("TextPolygon", [])
                bbox = [[p.get("X", 0), p.get("Y", 0)] for p in polygon] if polygon else [[0, 0], [0, 0], [0, 0], [0, 0]]
                confidence = item.get("Confidence", 1.0)
                if text.strip():
                    results.append((bbox, text, confidence))

        else:
            # 通用解析器
            items = response_data.get(text_field, [])
            for item in items:
                if isinstance(item, dict):
                    text = item.get("text", item.get(text_field, ""))
                    bbox = item.get("bbox", item.get(bbox_field, [[0, 0], [0, 0], [0, 0], [0, 0]]))
                    confidence = item.get("confidence", item.get(confidence_field, 1.0))
                elif isinstance(item, (list, tuple)):
                    # 简单格式: [[bbox], text, confidence]
                    bbox = item[0] if len(item) > 0 else [[0, 0], [0, 0], [0, 0], [0, 0]]
                    text = item[1] if len(item) > 1 else ""
                    confidence = item[2] if len(item) > 2 else 1.0
                else:
                    continue
                if text and str(text).strip():
                    results.append((bbox, str(text), float(confidence)))

        return results

    def _call_api(self, image_data: bytes) -> Optional[dict]:
        """调用 OCR API。"""
        import requests

        url = self._api_url
        if not url:
            raise RuntimeError("OCR API URL 未配置")

        headers = self._build_headers()
        body = self._build_request(image_data)

        for attempt in range(1, self._retry + 1):
            try:
                logger.debug("OCR API 请求 (尝试 %d/%d): %s", attempt, self._retry, url)
                response = requests.post(
                    url,
                    json=body,
                    headers=headers,
                    timeout=self._timeout,
                )
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                logger.warning("OCR API 请求失败 (尝试 %d/%d): %s", attempt, self._retry, e)
                if attempt == self._retry:
                    raise

        return None

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
            raise RuntimeError("OCR API 后端未初始化")

        import io

        # 将 PIL Image 转换为 bytes
        img_bytes = io.BytesIO()
        image.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        image_data = img_bytes.read()

        # 调用 API
        response_data = self._call_api(image_data)
        if not response_data:
            return []

        # 解析响应
        results = self._parse_response(response_data)

        # 转换为 LineMeta
        lines: list[LineMeta] = []
        for bbox, text, confidence in results:
            if not text or not text.strip():
                continue
            if confidence < min_confidence:
                logger.debug(
                    "跳过低置信度文本 '%s' (conf=%.3f)", text, confidence
                )
                continue

            line = _api_bbox_to_linemeta(bbox, text, page_num, dpi=dpi)
            lines.append(line)

        lines.sort(key=lambda line: (line.y0, line.x0))
        return lines

    def release(self) -> None:
        """释放资源（API 后端无需特殊清理）。"""
        pass


# ── 坐标转换 ──────────────────────────────────────────────


def _api_bbox_to_linemeta(
    bbox: Sequence[Sequence[float | int]],
    text: str,
    page_num: int,
    dpi: int = 300,
) -> LineMeta:
    """将 API 返回的 bbox 转换为 LineMeta。

    bbox 格式: [[x0,y0], [x1,y0], [x1,y1], [x0,y1]]
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
