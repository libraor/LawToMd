"""设备性能检测模块。

评估用户计算机的 CPU 处理能力、内存容量和图形处理性能，
据此推荐合适的 OCR 方案（高性能 PaddleOCR 或轻量版 RapidOCR）。

用法:
    from src.profiler import detect_device_profile, recommend_ocr_backend

    profile = detect_device_profile()
    backend = recommend_ocr_backend(profile)
    print(profile.summary())
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ── 性能等级 ──────────────────────────────────────────────


class PerformanceTier(Enum):
    """设备性能等级。"""

    HIGH = "high"
    LOW = "low"


# ── 设备性能档案 ──────────────────────────────────────────


# 高性能阈值
_CPU_CORE_THRESHOLD = 4
_MEMORY_GB_THRESHOLD = 8.0


@dataclass
class DeviceProfile:
    """设备性能档案，包含检测结果和推荐方案。"""

    cpu_cores: int
    memory_gb: float
    has_gpu: bool
    gpu_name: str
    tier: PerformanceTier

    @property
    def is_high_performance(self) -> bool:
        return self.tier == PerformanceTier.HIGH

    def summary(self) -> str:
        """返回人类可读的性能摘要，用于 CLI 展示。"""
        gpu_info = self.gpu_name if self.has_gpu else "无"
        tier_label = "高" if self.is_high_performance else "低"
        backend_name = "PaddleOCR (高性能)" if self.is_high_performance else "RapidOCR (轻量版)"

        lines = [
            "设备性能检测:",
            f"  CPU: {self.cpu_cores} 核 | 内存: {self.memory_gb:.1f} GB | GPU: {gpu_info}",
            f"  性能等级: {tier_label} | 推荐 OCR 方案: {backend_name}",
        ]

        # 推荐理由
        reasons = []
        if self.cpu_cores < _CPU_CORE_THRESHOLD:
            reasons.append(f"CPU 核心数 {self.cpu_cores} < {_CPU_CORE_THRESHOLD}")
        if self.memory_gb < _MEMORY_GB_THRESHOLD:
            reasons.append(f"内存 {self.memory_gb:.1f} GB < {_MEMORY_GB_THRESHOLD:.0f} GB")
        if not self.has_gpu:
            reasons.append("未检测到独立显卡")

        if reasons:
            lines.append(f"  推荐理由: {'; '.join(reasons)}")

        return "\n".join(lines)


# ── 检测函数 ──────────────────────────────────────────────


def _detect_cpu_cores() -> int:
    """检测 CPU 逻辑核心数。"""
    try:
        return os.cpu_count() or 1
    except Exception:
        return 1


def _detect_memory_gb() -> float:
    """检测系统总物理内存（GB）。"""
    system = platform.system()

    if system == "Windows":
        return _detect_memory_gb_windows()
    elif system == "Linux":
        return _detect_memory_gb_linux()
    elif system == "Darwin":
        return _detect_memory_gb_macos()

    return 0.0


def _detect_memory_gb_windows() -> float:
    """Windows 下检测内存。"""
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))  # type: ignore[attr-defined]
        return round(status.ullTotalPhys / (1024**3), 1)
    except Exception:
        logger.debug("Windows 内存检测失败", exc_info=True)
        return 0.0


def _detect_memory_gb_linux() -> float:
    """Linux 下检测内存。"""
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / (1024**2), 1)
    except Exception:
        logger.debug("Linux 内存检测失败", exc_info=True)
    return 0.0


def _detect_memory_gb_macos() -> float:
    """macOS 下检测内存。"""
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            bytes_total = int(result.stdout.strip())
            return round(bytes_total / (1024**3), 1)
    except Exception:
        logger.debug("macOS 内存检测失败", exc_info=True)
    return 0.0


def _detect_gpu() -> tuple[bool, str]:
    """检测是否具备独立显卡，返回 (has_discrete_gpu, gpu_name)。"""
    # 尝试 nvidia-smi（跨平台）
    gpu_name = _detect_gpu_nvidia_smi()
    if gpu_name:
        return True, gpu_name

    # 平台特定检测
    system = platform.system()
    if system == "Windows":
        return _detect_gpu_windows()
    elif system == "Linux":
        return _detect_gpu_linux()

    return False, ""


def _detect_gpu_nvidia_smi() -> str:
    """通过 nvidia-smi 检测 NVIDIA GPU。"""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[0].strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return ""


# 独立显卡关键词（用于区分集显和独显）
_DISCRETE_GPU_KEYWORDS = [
    "NVIDIA",
    "GeForce",
    "RTX",
    "GTX",
    "Quadro",
    "Radeon RX",
    "Radeon Pro",
    "Radeon(TM) RX",
    "Arc",
]

# 集成显卡关键词（排除项）
_INTEGRATED_GPU_KEYWORDS = [
    "Intel(R) UHD",
    "Intel(R) HD",
    "Intel(R) Iris",
    "Intel(R) Xe",
    "Radeon Vega",
    "Radeon(TM) Graphics",
    "Microsoft Basic Render",
]


def _is_discrete_gpu(gpu_name: str) -> bool:
    """判断 GPU 名称是否为独立显卡。"""
    name_lower = gpu_name.lower()
    for kw in _INTEGRATED_GPU_KEYWORDS:
        if kw.lower() in name_lower:
            return False
    for kw in _DISCRETE_GPU_KEYWORDS:
        if kw.lower() in name_lower:
            return True
    # 未知 GPU 默认视为非独显
    return False


def _detect_gpu_windows() -> tuple[bool, str]:
    """Windows 下通过 WMI 检测 GPU。"""
    try:
        result = subprocess.run(
            [
                "wmic",
                "path",
                "win32_VideoController",
                "get",
                "name",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            lines = [
                line.strip()
                for line in result.stdout.strip().split("\n")
                if line.strip()
            ]
            # 第一行是 "Name" 表头，跳过
            for gpu_name in lines[1:]:
                if _is_discrete_gpu(gpu_name):
                    return True, gpu_name
                # 记录第一个 GPU 名称作为回退
                if gpu_name:
                    logger.debug("检测到 GPU 但非独显: %s", gpu_name)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        logger.debug("Windows GPU 检测失败", exc_info=True)
    return False, ""


def _detect_gpu_linux() -> tuple[bool, str]:
    """Linux 下检测 GPU。"""
    # 尝试 lspci
    try:
        result = subprocess.run(
            ["lspci"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if "VGA" in line or "3D" in line or "Display" in line:
                    # 提取 GPU 名称
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        gpu_name = parts[1].strip()
                        if _is_discrete_gpu(gpu_name):
                            return True, gpu_name
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return False, ""


# ── 公共 API ──────────────────────────────────────────────


def detect_device_profile() -> DeviceProfile:
    """检测设备性能档案。

    Returns
    -------
    DeviceProfile
        包含 CPU 核心数、内存容量、GPU 信息和性能等级的档案。
    """
    cpu_cores = _detect_cpu_cores()
    memory_gb = _detect_memory_gb()
    has_gpu, gpu_name = _detect_gpu()

    # 综合判定性能等级：CPU ≥ 4 核 且 内存 ≥ 8GB 且 具备独立显卡
    tier = PerformanceTier.HIGH if (
        cpu_cores >= _CPU_CORE_THRESHOLD
        and memory_gb >= _MEMORY_GB_THRESHOLD
        and has_gpu
    ) else PerformanceTier.LOW

    logger.debug(
        "设备性能: CPU=%d核, 内存=%.1fGB, GPU=%s, 等级=%s",
        cpu_cores, memory_gb,
        gpu_name if has_gpu else "无",
        tier.value,
    )

    return DeviceProfile(
        cpu_cores=cpu_cores,
        memory_gb=memory_gb,
        has_gpu=has_gpu,
        gpu_name=gpu_name,
        tier=tier,
    )


def recommend_ocr_backend(profile: Optional[DeviceProfile] = None) -> str:
    """根据设备性能推荐 OCR 后端。

    Parameters
    ----------
    profile : DeviceProfile, optional
        设备性能档案，为 None 时自动检测。

    Returns
    -------
    str
        "paddle" 或 "lite"。
    """
    if profile is None:
        profile = detect_device_profile()

    if profile.tier == PerformanceTier.HIGH:
        return "paddle"
    return "lite"
