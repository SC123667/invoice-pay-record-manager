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
WINDOW_TITLE = "发票与支付记录管理工具"
APP_VERSION = "1.5.3"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
