from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "发票与支付记录管理"
CONFIG_DIR = Path.home() / ".invoice_manager_app"
CONFIG_FILE = CONFIG_DIR / "config.enc"
DEFAULT_LEVEL2_CATEGORIES = ["发票与支付记录"]
DEFAULT_LEVEL3_CATEGORIES = ["过路费", "加油", "住宿"]
DEFAULT_SOURCE_DIR_ENV = "INVOICE_MANAGER_DEFAULT_SOURCE_DIR"
DEFAULT_WECHAT_FILES_ROOT = (
    Path.home()
    / "Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"
)


def _detect_default_source_dir() -> str | None:
    configured = os.environ.get(DEFAULT_SOURCE_DIR_ENV, "").strip()
    if configured:
        return configured
    if not DEFAULT_WECHAT_FILES_ROOT.is_dir():
        return None
    candidates = [
        path
        for path in DEFAULT_WECHAT_FILES_ROOT.glob("*/msg/file")
        if path.is_dir()
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return str(candidates[0])


DEFAULT_INVOICE_SOURCE_DIR = _detect_default_source_dir()
DEFAULT_PAYMENT_SOURCE_DIR = DEFAULT_INVOICE_SOURCE_DIR
DEFAULT_RECOGNITION_SOURCE_DIR = DEFAULT_INVOICE_SOURCE_DIR
DEFAULT_SILICONFLOW_MODEL = "Qwen/Qwen3.5-397B-A17B"
LEGACY_DEFAULT_SILICONFLOW_MODELS = (
    "Qwen/Qwen3-VL-32B-Instruct",
    "Qwen/Qwen2.5-VL-72B-Instruct",
)
RECOMMENDED_SILICONFLOW_VISION_MODELS = (
    DEFAULT_SILICONFLOW_MODEL,
    "Qwen/Qwen3.6-35B-A3B",
    "Qwen/Qwen3.6-27B",
    "Qwen/Qwen3.5-122B-A10B",
    "Qwen/Qwen3.5-35B-A3B",
    "Qwen/Qwen3.5-27B",
    "Qwen/Qwen3.5-9B",
    "Qwen/Qwen3.5-4B",
    "Qwen/Qwen3-VL-235B-A22B-Instruct",
    "Qwen/Qwen3-VL-235B-A22B-Thinking",
    "Qwen/Qwen3-VL-30B-A3B-Instruct",
    "Qwen/Qwen3-VL-30B-A3B-Thinking",
    "Qwen/Qwen3-VL-32B-Instruct",
    "Qwen/Qwen3-VL-32B-Thinking",
    "Qwen/Qwen3-VL-8B-Instruct",
    "Qwen/Qwen2.5-VL-32B-Instruct",
    "Qwen/Qwen2.5-VL-72B-Instruct",
)
WINDOW_TITLE = "发票与支付记录管理工具"
APP_VERSION = "1.5.15"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
