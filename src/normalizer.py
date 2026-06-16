"""文本规范化模块。

处理全角/半角统一、OCR 常见错误修正、自定义替换规则。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

# 全角→半角映射（仅实际需要转换的字符；中文标点保留全角）
FULLWIDTH_MAP = str.maketrans({
    "　": " ",    # 全角空格→半角
    "─": "-",     # 长破折号
    "—": "-",     # 破折号
})

# ── 替换配置加载 ──────────────────────────────────────────

_config_lock = Lock()
_replacements: list[tuple[re.Pattern, str]] | None = None
_header_footer_sigs: list[re.Pattern] | None = None


def load_replace_config() -> None:
    """加载 config/replace.yaml 中的替换规则（仅首次调用时加载，线程安全）。"""
    global _replacements, _header_footer_sigs

    if _replacements is not None:
        return

    with _config_lock:
        # 双重检查：获取锁后再检查一次
        if _replacements is not None:
            return

        config_path = Path(__file__).resolve().parent.parent / "config" / "replace.yaml"
        replacements: list[tuple[re.Pattern, str]] = []
        header_footer_sigs: list[re.Pattern] = []

        if config_path.exists():
            try:
                import yaml

                with open(config_path, encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)

                for item in cfg.get("replacements", []):
                    if isinstance(item, (list, tuple)) and len(item) == 2:
                        replacements.append((re.compile(re.escape(item[0])), item[1]))

                for sig in cfg.get("header_footer_signatures", []):
                    header_footer_sigs.append(re.compile(re.escape(sig)))

                logger.debug("加载替换规则: %d 条, 页眉页脚签名: %d 条",
                             len(replacements), len(header_footer_sigs))
            except Exception as e:
                logger.warning("加载 replace.yaml 失败: %s", e)

        _replacements = replacements
        _header_footer_sigs = header_footer_sigs


def get_replacements() -> list[tuple[re.Pattern, str]]:
    """获取已加载的自定义替换规则。"""
    load_replace_config()
    return _replacements or []


def get_header_footer_sigs() -> list[re.Pattern]:
    """获取已加载的页眉页脚签名。"""
    load_replace_config()
    return _header_footer_sigs or []


def normalize_text(text: str) -> str:
    """对提取的文本进行规范化处理。

    处理内容：
    - 全角空格→半角空格
    - OCR 常见误识别修正
    - 自定义替换规则（config/replace.yaml）

    注意：法律文本中的中文标点（，。：；等）保留全角，不做转换。
    """
    # 全角字符规范化（空格、破折号等）
    text = text.translate(FULLWIDTH_MAP)

    # 替换规则（含 OCR 误识别修正，统一由 replace.yaml 配置）
    for pat, repl in get_replacements():
        text = pat.sub(repl, text)

    # 多余空白压缩
    text = re.sub(r" {2,}", " ", text)

    return text.strip()
