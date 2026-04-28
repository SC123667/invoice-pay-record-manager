from __future__ import annotations

import os
import shlex
import shutil
import calendar
import json
import re
import tempfile
import threading
from datetime import date, datetime, timedelta
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - optional dependency
    TkinterDnD = None  # type: ignore[assignment]
    DND_FILES = "DND_Files"


class UserCancelledError(Exception):
    """Raised when the user aborts an interactive prompt."""

from ..api_client import (
    RecognitionAPIError,
    call_recognition_api,
    extract_date_from_payload,
)
from ..config_manager import ConfigManager
from ..constants import (
    DEFAULT_SILICONFLOW_MODEL,
    LEGACY_DEFAULT_SILICONFLOW_MODELS,
    RECOMMENDED_SILICONFLOW_VISION_MODELS,
    WINDOW_TITLE,
)
from ..data_models import AppConfig
from ..encryption import EncryptionError
from ..regions import REGIONS
from .dialogs import ask_password, ask_text


INVALID_CHARS = set('<>:"\\|?*')
INVOICE_TEXT_HINTS: Tuple[Tuple[str, int], ...] = (
    ("发票", 3),
    ("电子发票", 5),
    ("数电票", 5),
    ("普通发票", 4),
    ("增值税发票", 5),
    ("开票", 3),
    ("开票日期", 5),
    ("购买方信息", 4),
    ("销售方信息", 4),
    ("销方", 2),
    ("购方", 2),
    ("税号", 3),
    ("纳税人识别号", 4),
    ("价税合计", 2),
    ("税额", 2),
    ("发票号码", 3),
    ("发票代码", 3),
    ("行程单", 3),
    ("报销凭证", 3),
    ("invoice", 3),
    ("vat", 2),
    ("五金", 3),
    ("劳保", 3),
    ("劳保用品", 2),
)
PAYMENT_TEXT_HINTS: Tuple[Tuple[str, int], ...] = (
    ("支付", 3),
    ("支付成功", 6),
    ("当前状态", 3),
    ("付款成功", 6),
    ("转账成功", 6),
    ("付款", 3),
    ("收款", 3),
    ("支付时间", 5),
    ("转账时间", 5),
    ("交易时间", 4),
    ("支付方式", 5),
    ("交易单号", 5),
    ("转账单号", 5),
    ("商户单号", 4),
    ("收单机构", 4),
    ("微信支付", 4),
    ("支付宝", 4),
    ("财付通", 4),
    ("扫码付款", 4),
    ("二维码收款", 4),
    ("交易", 2),
    ("流水", 2),
    ("POS", 2),
    ("银联", 2),
    ("银行卡", 2),
    ("商户", 2),
    ("终端", 1),
    ("payment", 3),
    ("receipt", 2),
)
INVOICE_DOCUMENT_TYPE_VALUES = {
    "invoice",
    "发票",
    "电子发票",
    "普通发票",
    "数电票",
    "数电普票",
    "electronic_invoice",
}
PAYMENT_DOCUMENT_TYPE_VALUES = {
    "payment_proof",
    "payment",
    "payment_record",
    "pay_record",
    "支付凭证",
    "支付记录",
    "付款凭证",
    "付款记录",
    "转账凭证",
    "交易记录",
}
DOCUMENT_TYPE_KEYS = (
    "document_type",
    "doc_type",
    "document_kind",
    "type",
    "票据类型",
    "凭证类型",
)

CATEGORY_ORDER = ["加油", "住宿", "过路费", "五金"]
CATEGORY_KEYWORDS = {
    "加油": [
        "加油",
        "加油站",
        "汽油",
        "柴油",
        "燃油",
        "成品油",
        "油费",
        "加气",
        "fuel",
        "gasoline",
        "diesel",
        "92#",
        "95#",
        "中石化",
        "中国石化",
        "中石油",
        "中国石油",
        "sinopec",
        "petrochina",
        "cnpc",
    ],
    "住宿": [
        "住宿",
        "宾馆",
        "酒店",
        "客房",
        "入住",
        "旅店",
        "旅馆",
        "客栈",
        "hotel",
        "inn",
        "motel",
        "room",
        "房费",
    ],
    "过路费": [
        "过路费",
        "通行费",
        "过桥费",
        "高速",
        "高速费",
        "高速公路",
        "收费站",
        "路桥",
        "路桥费",
        "toll",
        "etc",
        "etc扣费",
        "通行",
        "通行流水",
    ],
    "五金": [
        "五金",
        "劳保",
        "工具",
        "配件",
        "耗材",
        "电瓶",
        "电池",
        "铁锹",
        "铁鍬",
        "扳手",
        "锤",
        "螺丝",
        "螺栓",
        "螺母",
        "钳",
        "刀",
        "hardware",
        "砂轮",
        "焊机",
        "焊条",
        "安全帽",
        "手套",
        "口罩",
        "劳保用品",
    ],
}
DEFAULT_CATEGORY_FALLBACK = "其他"
DEFAULT_SF_MODEL = DEFAULT_SILICONFLOW_MODEL
LEGACY_DEFAULT_SF_MODELS = LEGACY_DEFAULT_SILICONFLOW_MODELS
AMOUNT_KEYWORDS = (
    "金额",
    "价税合计",
    "合计",
    "支付金额",
    "转账金额",
    "付款金额",
    "实付金额",
    "实际支付",
    "total",
    "amount",
    "total_amount",
    "价款",
    "发票金额",
)
_AMOUNT_PATTERN = re.compile(r"-?\d+(?:[.,]\d{1,2})?")


def sanitize_folder_name(name: str) -> str:
    cleaned = name.replace(os.sep, " ")
    if os.altsep:
        cleaned = cleaned.replace(os.altsep, " ")
    cleaned = cleaned.replace("/", " ")
    cleaned = cleaned.replace('..', ' ')
    cleaned = "".join(ch for ch in cleaned if ord(ch) >= 32)
    return cleaned.strip()


def is_valid_folder_name(name: str) -> bool:
    return bool(name) and not any(ch in INVALID_CHARS for ch in name)


class SettingsWindow(tk.Toplevel):
    def __init__(self, master: "MainWindow") -> None:
        super().__init__(master)
        self.master = master
        self.title("设置")
        self.resizable(False, False)
        self.configure(padx=16, pady=16)

        ttk.Label(self, text="当前根目录:").grid(row=0, column=0, sticky="w")
        self.path_var = tk.StringVar(value=self.master.get_root_path_display())
        self.path_label = ttk.Label(self, textvariable=self.path_var, width=50)
        self.path_label.grid(row=1, column=0, columnspan=2, sticky="we", pady=(4, 10))

        ttk.Button(self, text="选择新的根目录", command=self.select_new_root).grid(
            row=2, column=0, sticky="w"
        )
        ttk.Button(self, text="更改主密码", command=self.change_password).grid(
            row=2, column=1, sticky="e"
        )

        self.invoice_dir_var = tk.StringVar(
            value=self.master.app_config.invoice_source_dir or ""
        )
        self.payment_dir_var = tk.StringVar(
            value=self.master.app_config.payment_source_dir or ""
        )
        self.recognition_dir_var = tk.StringVar(
            value=self.master.app_config.recognition_source_dir or ""
        )

        folder_frame = ttk.LabelFrame(self, text="默认文件夹")
        folder_frame.grid(row=3, column=0, columnspan=2, sticky="we", pady=(12, 0))

        ttk.Label(folder_frame, text="发票上传来源:").grid(row=0, column=0, sticky="w")
        ttk.Entry(folder_frame, textvariable=self.invoice_dir_var, width=40).grid(
            row=0, column=1, sticky="we", padx=(4, 4)
        )
        ttk.Button(
            folder_frame,
            text="选择...",
            command=self.select_invoice_source_dir,
        ).grid(row=0, column=2, padx=(4, 0))

        ttk.Label(folder_frame, text="支付凭证来源:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(folder_frame, textvariable=self.payment_dir_var, width=40).grid(
            row=1, column=1, sticky="we", padx=(4, 4), pady=(6, 0)
        )
        ttk.Button(
            folder_frame,
            text="选择...",
            command=self.select_payment_source_dir,
        ).grid(row=1, column=2, padx=(4, 0), pady=(6, 0))

        ttk.Label(folder_frame, text="识别文件默认位置:").grid(
            row=2, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Entry(folder_frame, textvariable=self.recognition_dir_var, width=40).grid(
            row=2, column=1, sticky="we", padx=(4, 4), pady=(6, 0)
        )
        ttk.Button(
            folder_frame,
            text="选择...",
            command=self.select_recognition_source_dir,
        ).grid(row=2, column=2, padx=(4, 0), pady=(6, 0))

        folder_frame.grid_columnconfigure(1, weight=1)

        api_frame = ttk.LabelFrame(self, text="识别接口设置")
        api_frame.grid(row=4, column=0, columnspan=2, sticky="we", pady=(12, 0))

        self.app_id_var = tk.StringVar(value=self.master.app_config.api_app_id or "")
        self.app_secret_var = tk.StringVar(value=self.master.app_config.api_app_secret or "")
        self.token_var = tk.StringVar(value=self.master.app_config.api_token or "")
        self.endpoint_var = tk.StringVar(value=self.master.app_config.api_endpoint or "")
        extra_params = self.master.app_config.api_extra_params
        extra_text = (
            json.dumps(extra_params, ensure_ascii=False)
            if extra_params
            else ""
        )
        self.extra_params_var = tk.StringVar(value=extra_text)
        self.sf_enabled_var = tk.BooleanVar(value=bool(self.master.app_config.use_siliconflow))
        self.sf_token_var = tk.StringVar(
            value=self.master.app_config.siliconflow_token or ""
        )
        current_sf_model = (
            self.master.app_config.siliconflow_model
            or DEFAULT_SF_MODEL
        )
        if current_sf_model in LEGACY_DEFAULT_SF_MODELS:
            current_sf_model = DEFAULT_SF_MODEL
        self.sf_model_history = list(
            self.master.app_config.siliconflow_model_history or []
        )
        self.sf_model_history = self._unique_models(
            list(RECOMMENDED_SILICONFLOW_VISION_MODELS)
            + self.sf_model_history
            + [current_sf_model]
        )
        self.sf_model_var = tk.StringVar(value=current_sf_model)
        self.sf_prompt_var = tk.StringVar(
            value=self.master.app_config.siliconflow_prompt or ""
        )

        ttk.Label(api_frame, text="APP ID:").grid(row=0, column=0, sticky="w")
        ttk.Entry(api_frame, textvariable=self.app_id_var, width=40).grid(
            row=0, column=1, sticky="we", pady=(4, 0)
        )

        ttk.Label(api_frame, text="APP Secret:").grid(row=1, column=0, sticky="w")
        ttk.Entry(api_frame, textvariable=self.app_secret_var, show="*", width=40).grid(
            row=1, column=1, sticky="we", pady=(4, 0)
        )

        ttk.Label(api_frame, text="UAT Token(可选):").grid(row=2, column=0, sticky="w")
        ttk.Entry(api_frame, textvariable=self.token_var, width=40).grid(
            row=2, column=1, sticky="we", pady=(4, 0)
        )

        ttk.Label(api_frame, text="接口地址:").grid(row=3, column=0, sticky="w")
        ttk.Entry(api_frame, textvariable=self.endpoint_var, width=40).grid(
            row=3, column=1, sticky="we", pady=(4, 0)
        )

        ttk.Label(api_frame, text="额外参数(JSON，可选):").grid(row=4, column=0, sticky="nw")
        ttk.Entry(api_frame, textvariable=self.extra_params_var, width=40).grid(
            row=4, column=1, sticky="we", pady=(4, 0)
        )

        ttk.Button(api_frame, text="保存识别设置", command=self.save_api_settings).grid(
            row=5, column=1, sticky="e", pady=(8, 0)
        )
        api_frame.grid_columnconfigure(1, weight=1)

        sf_frame = ttk.LabelFrame(self, text="硅基流动设置")
        sf_frame.grid(row=5, column=0, columnspan=2, sticky="we", pady=(12, 0))
        ttk.Checkbutton(
            sf_frame,
            text="使用硅基流动进行识别",
            variable=self.sf_enabled_var,
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(sf_frame, text="API Token:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(sf_frame, textvariable=self.sf_token_var, width=40).grid(
            row=1, column=1, sticky="we", pady=(6, 0)
        )
        ttk.Label(sf_frame, text="模型名称:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.sf_model_combo = ttk.Combobox(
            sf_frame,
            textvariable=self.sf_model_var,
            values=self.sf_model_history,
            width=40,
            state="normal",
        )
        self.sf_model_combo.grid(row=2, column=1, sticky="we", pady=(6, 0))
        ttk.Label(sf_frame, text="用户提示语(可选):").grid(row=3, column=0, sticky="nw", pady=(6, 0))
        ttk.Entry(sf_frame, textvariable=self.sf_prompt_var, width=40).grid(
            row=3, column=1, sticky="we", pady=(6, 0)
        )
        sf_frame.grid_columnconfigure(1, weight=1)

        ttk.Separator(self, orient="horizontal").grid(
            row=6, column=0, columnspan=2, sticky="we", pady=12
        )

        ttk.Button(self, text="保存设置", command=self.save_all_settings).grid(
            row=7, column=0, sticky="w"
        )
        ttk.Button(self, text="关闭", command=self.destroy).grid(row=7, column=1, sticky="e")
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

    def select_new_root(self) -> None:
        new_path = filedialog.askdirectory(title="选择根目录", parent=self)
        if not new_path:
            return
        self.master.set_root_path(new_path)
        self.path_var.set(self.master.get_root_path_display())

    def change_password(self) -> None:
        current = ask_password(self, "输入当前密码", "请输入当前主密码:")
        if not current:
            return
        try:
            _ = self.master.config_manager.load(current)
        except EncryptionError as exc:
            messagebox.showerror("错误", str(exc), parent=self)
            return
        new_password = ask_password(self, "设置新密码", "请输入新的主密码:", confirm=True)
        if not new_password:
            return
        try:
            self.master.update_password(current, new_password)
            messagebox.showinfo("成功", "密码已更新", parent=self)
        except EncryptionError as exc:
            messagebox.showerror("错误", str(exc), parent=self)

    def select_invoice_source_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择发票文件所在文件夹", parent=self)
        if selected:
            self.invoice_dir_var.set(selected)

    def select_payment_source_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择支付凭证所在文件夹", parent=self)
        if selected:
            self.payment_dir_var.set(selected)

    def select_recognition_source_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择识别文件默认文件夹", parent=self)
        if selected:
            self.recognition_dir_var.set(selected)

    def save_all_settings(self) -> None:
        self.save_api_settings()

    @staticmethod
    def _likely_vlm_model(name: str) -> bool:
        lowered = name.lower()
        normalized = name.strip()
        keywords = ("vl", "vision", "multimodal", "image", "qwen3.5", "qwen3.6")
        return (
            normalized in RECOMMENDED_SILICONFLOW_VISION_MODELS
            or any(keyword in lowered for keyword in keywords)
        )

    @staticmethod
    def _unique_models(models: Iterable[str]) -> List[str]:
        result: List[str] = []
        seen = set()
        for model in models:
            normalized = str(model).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    def save_api_settings(self) -> None:
        app_id = self.app_id_var.get().strip() or None
        app_secret = self.app_secret_var.get().strip() or None
        token = self.token_var.get().strip() or None
        endpoint = self.endpoint_var.get().strip() or None
        raw_extra = self.extra_params_var.get().strip()

        if raw_extra:
            try:
                parsed_extra = json.loads(raw_extra)
            except json.JSONDecodeError as exc:
                messagebox.showerror(
                    "错误", f"额外参数需为JSON对象: {exc}", parent=self
                )
                return
            if not isinstance(parsed_extra, dict):
                messagebox.showerror(
                    "错误", "额外参数必须为JSON格式的对象 (形如{'key':'value'})",
                    parent=self,
                )
                return
            extra_params = {str(key): str(value) for key, value in parsed_extra.items()}
        else:
            extra_params = {}

        use_siliconflow = self.sf_enabled_var.get()
        sf_token = self.sf_token_var.get().strip() or None
        sf_model = self.sf_model_var.get().strip() or DEFAULT_SF_MODEL
        sf_prompt = self.sf_prompt_var.get().strip() or None
        if use_siliconflow and not sf_token:
            messagebox.showerror("错误", "启用硅基流动时必须填写API Token", parent=self)
            return
        if not sf_model:
            sf_model = DEFAULT_SF_MODEL
        if use_siliconflow and not self._likely_vlm_model(sf_model):
            proceed = messagebox.askyesno(
                "模型确认",
                (
                    "所选模型看起来不像是视觉语言模型(VLM)，可能无法处理图片。\n"
                    "确定仍要使用该模型吗？选择“否”可返回修改。"
                ),
                parent=self,
            )
            if not proceed:
                return

        self.master.app_config.api_app_id = app_id
        self.master.app_config.api_app_secret = app_secret
        self.master.app_config.api_token = token
        self.master.app_config.api_endpoint = endpoint
        self.master.app_config.api_extra_params = extra_params
        self.master.app_config.invoice_source_dir = (
            self.invoice_dir_var.get().strip() or None
        )
        self.master.app_config.payment_source_dir = (
            self.payment_dir_var.get().strip() or None
        )
        self.master.app_config.recognition_source_dir = (
            self.recognition_dir_var.get().strip() or None
        )
        self.master.app_config.use_siliconflow = use_siliconflow
        self.master.app_config.siliconflow_token = sf_token
        self.master.app_config.siliconflow_model = sf_model
        self.master.app_config.siliconflow_prompt = sf_prompt
        self.master.app_config.add_siliconflow_model(sf_model)
        self.sf_model_history = list(self.master.app_config.siliconflow_model_history)
        self.sf_model_combo.configure(values=self.sf_model_history)
        self.master.save_config()
        self.master._update_state()
        messagebox.showinfo("成功", "识别接口设置已保存", parent=self)


class MainWindow(tk.Tk):
    def __init__(self, config_manager: ConfigManager, config: AppConfig, password: str) -> None:
        super().__init__()
        self.config_manager = config_manager
        self.app_config = config
        self.password = password
        self.current_region_path: Optional[Path] = None
        self.current_category_path: Optional[Path] = None
        self.current_level3_path: Optional[Path] = None
        self.current_date_path: Optional[Path] = None
        self._range_info: Optional[Tuple[date, date, str]] = None
        self._range_end_date: Optional[date] = None
        self._drag_supported = self._init_drag_support()
        self._batch_stop_requested = False
        self._batch_running = False
        self._batch_amount_stats: Dict[str, float] = {}
        self._batch_files: List[Path] = []
        self._batch_total = 0
        self._batch_index = 0
        self._batch_success_count = 0
        self._batch_skipped_count = 0
        self._batch_stopped_early = False
        self._batch_public_card = False
        self._batch_saved_records: List[Dict[str, Any]] = []
        self._batch_amount_only_pair_reports: List[str] = []
        self._batch_ambiguous_pair_reports: List[str] = []
        self._recognition_logs: List[str] = []
        self._log_window: Optional[tk.Toplevel] = None
        self._log_text: Optional[tk.Text] = None
        self._debug_payload_path = (
            Path(__file__).resolve().parents[2] / "recognition_debug.json"
        )

        self.title(WINDOW_TITLE)
        self.geometry("900x620")
        self.minsize(780, 520)
        self.configure(padx=16, pady=16)

        self.root_path_var = tk.StringVar(value=self.get_root_path_display())
        self.status_var = tk.StringVar(value="欢迎使用发票与支付记录管理工具")

        self.region_var = tk.StringVar()
        self.level2_var = tk.StringVar()
        self.level3_var = tk.StringVar()
        self.year_var = tk.StringVar()
        self.month_var = tk.StringVar()
        self.day_var = tk.StringVar()
        self.is_public_card_var = tk.BooleanVar(value=False)

        self._closing = False
        self._build_menu()
        self._build_layout()
        self._setup_drag_and_drop()
        self._refresh_comboboxes()
        self._restore_last_state()
        self._update_state()
        self._remember_state()
        self.protocol("WM_DELETE_WINDOW", self.request_exit)
        self.is_public_card_var.trace_add("write", lambda *_: self._remember_state())

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)
        app_menu = tk.Menu(menu_bar, tearoff=0)
        app_menu.add_command(label="设置", command=self.open_settings)
        app_menu.add_separator()
        app_menu.add_command(label="退出", command=self.request_exit)
        menu_bar.add_cascade(label="应用", menu=app_menu)
        self.config(menu=menu_bar)

    def _build_layout(self) -> None:
        style = ttk.Style()
        try:
            available = set(style.theme_names())
            if 'aqua' in available:
                style.theme_use('aqua')
        except tk.TclError:
            pass

        root_frame = ttk.LabelFrame(self, text="根目录设置")
        root_frame.grid(row=0, column=0, sticky="nwe", padx=4, pady=4)
        ttk.Label(root_frame, text="当前根目录:").grid(row=0, column=0, sticky="w")
        ttk.Label(root_frame, textvariable=self.root_path_var, width=60).grid(
            row=1, column=0, sticky="w", pady=(4, 0)
        )
        ttk.Button(root_frame, text="打开设置", command=self.open_settings).grid(
            row=1, column=1, padx=(12, 0)
        )
        root_frame.grid_columnconfigure(0, weight=1)

        region_frame = ttk.LabelFrame(self, text="选择地区")
        region_frame.grid(row=1, column=0, sticky="nwe", padx=4, pady=(8, 4))
        ttk.Label(region_frame, text="省/自治区/直辖市:").grid(row=0, column=0, sticky="w")
        self.region_combo = ttk.Combobox(
            region_frame,
            textvariable=self.region_var,
            values=REGIONS,
            state="readonly",
        )
        self.region_combo.grid(row=1, column=0, sticky="we", pady=(4, 0))
        self.region_combo.bind("<<ComboboxSelected>>", self.handle_region_selection)
        region_frame.grid_columnconfigure(0, weight=1)

        level2_frame = ttk.LabelFrame(self, text="一级类别")
        level2_frame.grid(row=2, column=0, sticky="nwe", padx=4, pady=(8, 4))
        ttk.Label(level2_frame, text="类别:").grid(row=0, column=0, sticky="w")
        self.level2_combo = ttk.Combobox(
            level2_frame,
            textvariable=self.level2_var,
            state="readonly",
        )
        self.level2_combo.grid(row=1, column=0, sticky="we", pady=(4, 0))
        self.level2_combo.bind("<<ComboboxSelected>>", self.handle_level2_selection)
        ttk.Button(level2_frame, text="新增类别", command=self.add_level2_category).grid(
            row=1, column=1, padx=(12, 0)
        )
        level2_frame.grid_columnconfigure(0, weight=1)

        level3_frame = ttk.LabelFrame(self, text="二级类别")
        level3_frame.grid(row=3, column=0, sticky="nwe", padx=4, pady=(8, 4))
        ttk.Label(level3_frame, text="类别:").grid(row=0, column=0, sticky="w")
        self.level3_combo = ttk.Combobox(
            level3_frame,
            textvariable=self.level3_var,
            state="readonly",
        )
        self.level3_combo.grid(row=1, column=0, sticky="we", pady=(4, 0))
        self.level3_combo.bind("<<ComboboxSelected>>", self.handle_level3_selection)
        ttk.Button(level3_frame, text="新增类别", command=self.add_level3_category).grid(
            row=1, column=1, padx=(12, 0)
        )
        level3_frame.grid_columnconfigure(0, weight=1)

        date_frame = ttk.LabelFrame(self, text="日期选择")
        date_frame.grid(row=4, column=0, sticky="nwe", padx=4, pady=(8, 4))
        ttk.Label(date_frame, text="年份:").grid(row=0, column=0, sticky="w")
        self.year_combo = ttk.Combobox(date_frame, textvariable=self.year_var, state="disabled", width=6)
        self.year_combo.grid(row=0, column=1, padx=(6, 12))
        self.year_combo.bind("<<ComboboxSelected>>", self.handle_year_selection)

        ttk.Label(date_frame, text="月份:").grid(row=0, column=2, sticky="w")
        self.month_combo = ttk.Combobox(date_frame, textvariable=self.month_var, state="disabled", width=4)
        self.month_combo.grid(row=0, column=3, padx=(6, 12))
        self.month_combo.bind("<<ComboboxSelected>>", self.handle_month_selection)

        ttk.Label(date_frame, text="日期:").grid(row=0, column=4, sticky="w")
        self.day_combo = ttk.Combobox(date_frame, textvariable=self.day_var, state="disabled", width=4)
        self.day_combo.grid(row=0, column=5, padx=(6, 0))
        self.day_combo.bind("<<ComboboxSelected>>", self.handle_day_selection)
        self.detect_date_btn = ttk.Button(
            date_frame,
            text="识别凭证日期",
            command=self.detect_document_date,
            state="disabled",
        )
        self.detect_date_btn.grid(row=0, column=6, padx=(12, 0))
        self.batch_detect_btn = ttk.Button(
            date_frame,
            text="批量识别文件夹",
            command=self.detect_document_folder_batch,
            state="disabled",
        )
        self.batch_detect_btn.grid(row=0, column=7, padx=(12, 0))
        self.stop_batch_btn = ttk.Button(
            date_frame,
            text="停止批量",
            command=self.request_stop_batch,
            state="disabled",
        )
        self.stop_batch_btn.grid(row=0, column=8, padx=(12, 0))
        self.open_log_btn = ttk.Button(
            date_frame,
            text="识别日志",
            command=self.open_recognition_log,
        )
        self.open_log_btn.grid(row=0, column=9, padx=(12, 0))
        date_frame.grid_columnconfigure(10, weight=1)

        upload_frame = ttk.LabelFrame(self, text="上传凭证")
        upload_frame.grid(row=5, column=0, sticky="nwe", padx=4, pady=(8, 4))
        self.public_card_check = ttk.Checkbutton(
            upload_frame, text="公务卡交易", variable=self.is_public_card_var, state="disabled"
        )
        self.public_card_check.grid(row=0, column=0, sticky="w")

        self.upload_invoice_btn = ttk.Button(
            upload_frame, text="上传发票", command=self.upload_invoice, state="disabled"
        )
        self.upload_invoice_btn.grid(row=0, column=1, padx=(12, 0))

        self.upload_payment_btn = ttk.Button(
            upload_frame, text="上传支付凭证", command=self.upload_payment_proof, state="disabled"
        )
        self.upload_payment_btn.grid(row=0, column=2, padx=(12, 0))
        if TkinterDnD:
            self.drag_drop_label = tk.Label(
                upload_frame,
                text="拖拽功能初始化中...",
                relief="ridge",
                padx=8,
                pady=8,
                anchor="center",
                borderwidth=1,
            )
        else:
            self.drag_drop_label = ttk.Label(
                upload_frame,
                text="拖拽功能初始化中...",
                relief="ridge",
                padding=8,
                anchor="center",
            )
        self.drag_drop_label.grid(row=1, column=0, columnspan=3, sticky="we", pady=(12, 4))
        upload_frame.grid_columnconfigure(3, weight=1)

        status_frame = ttk.Frame(self)
        status_frame.grid(row=6, column=0, sticky="we", padx=4, pady=(12, 0))
        ttk.Separator(status_frame, orient="horizontal").grid(row=0, column=0, sticky="we")
        ttk.Label(status_frame, textvariable=self.status_var).grid(row=1, column=0, sticky="w", pady=(6, 0))
        status_frame.grid_columnconfigure(0, weight=1)

        self.grid_rowconfigure(6, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._populate_year_options()

    def _init_drag_support(self) -> bool:
        if not TkinterDnD:
            return False
        try:
            version = TkinterDnD._require(self)  # type: ignore[attr-defined]
        except Exception:
            return False
        else:
            setattr(self, "TkdndVersion", version)
            return True

    def _setup_drag_and_drop(self) -> None:
        widget = getattr(self, "drag_drop_label", None)
        if widget is None:
            return
        if not self._drag_supported:
            widget.configure(text="当前环境暂不支持拖拽识别", foreground="gray")
            return
        if not hasattr(widget, "drop_target_register"):
            widget.configure(text="当前环境暂不支持拖拽识别", foreground="gray")
            self._drag_supported = False
            return
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._handle_drop_for_recognition)
            widget.dnd_bind("<<DropEnter>>", lambda _: widget.configure(relief="sunken"))
            widget.dnd_bind("<<DropLeave>>", lambda _: widget.configure(relief="ridge"))
            widget.configure(text="将文件拖入此处识别日期")
            self._drag_supported = True
        except (tk.TclError, AttributeError):
            widget.configure(text="当前环境暂不支持拖拽识别", foreground="gray")
            self._drag_supported = False

    def open_recognition_log(self) -> None:
        if self._log_window is not None and self._log_window.winfo_exists():
            self._log_window.lift()
            return

        window = tk.Toplevel(self)
        window.title("识别日志")
        window.geometry("880x520")
        window.minsize(680, 360)
        window.protocol("WM_DELETE_WINDOW", self._close_log_window)

        toolbar = ttk.Frame(window)
        toolbar.grid(row=0, column=0, sticky="we", padx=10, pady=(10, 6))
        ttk.Button(toolbar, text="清空日志", command=self.clear_recognition_log).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(toolbar, text="识别过程会实时追加到下方").grid(
            row=0, column=1, sticky="w", padx=(12, 0)
        )
        toolbar.grid_columnconfigure(2, weight=1)

        log_text = scrolledtext.ScrolledText(
            window,
            wrap="word",
            height=20,
            state="disabled",
            font=("Menlo", 12),
        )
        log_text.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        window.grid_rowconfigure(1, weight=1)
        window.grid_columnconfigure(0, weight=1)

        self._log_window = window
        self._log_text = log_text
        self._refresh_log_window()

    def _close_log_window(self) -> None:
        if self._log_window is not None and self._log_window.winfo_exists():
            self._log_window.destroy()
        self._log_window = None
        self._log_text = None

    def clear_recognition_log(self) -> None:
        self._recognition_logs = []
        self._refresh_log_window()

    def _append_recognition_log(self, message: str) -> None:
        if "_recognition_logs" not in self.__dict__:
            self.__dict__["_recognition_logs"] = []
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        self._recognition_logs.append(entry)
        self._refresh_log_window(append_only=entry)

    def _refresh_log_window(self, append_only: Optional[str] = None) -> None:
        log_text = self.__dict__.get("_log_text")
        if log_text is None:
            return
        try:
            log_text.configure(state="normal")
            if append_only is None:
                log_text.delete("1.0", tk.END)
                if self._recognition_logs:
                    log_text.insert(tk.END, "\n".join(self._recognition_logs) + "\n")
            else:
                log_text.insert(tk.END, append_only + "\n")
            log_text.configure(state="disabled")
            log_text.see(tk.END)
        except tk.TclError:
            self._log_text = None

    def _summarize_payload_for_log(self, payload: Mapping[str, Any]) -> str:
        summary: Dict[str, Any] = {}
        document_type = self._extract_model_document_type(payload)
        if document_type:
            is_invoice, evidence = document_type
            summary["document_type"] = "发票" if is_invoice else "支付凭证"
            summary["document_type_evidence"] = evidence
        detected_dt = extract_date_from_payload(payload)
        if detected_dt:
            summary["date"] = detected_dt.astimezone().date().isoformat()
        category = self._infer_invoice_category(payload, Path(""))
        if category:
            summary["category"] = category
        amount = self._extract_amount_from_payload(payload)
        if amount is not None:
            summary["amount"] = f"{amount:.2f}"
        if not summary:
            summary["payload_keys"] = list(payload.keys())[:12]
        raw = json.dumps(summary, ensure_ascii=False)
        return raw[:1000] + ("..." if len(raw) > 1000 else "")

    def _restore_last_state(self) -> None:
        config = self.app_config
        if not config.root_path:
            return
        try:
            root = Path(config.root_path)
        except OSError:
            return
        if not root.exists():
            return
        region = config.last_region
        region_ok = bool(region and region in self.region_combo["values"])
        if region_ok:
            self.region_var.set(region)
            self.handle_region_selection()

        level2 = config.last_level2
        level2_ok = region_ok and level2 and level2 in self.level2_combo["values"]
        if level2_ok:
            self.level2_var.set(level2)
            self.handle_level2_selection()

        level3 = config.last_level3
        level3_ok = level2_ok and level3 and level3 in self.level3_combo["values"]
        if level3_ok:
            self.level3_var.set(level3)
            self.handle_level3_selection()

        year = config.last_year
        month = config.last_month
        day = config.last_day
        valid_date = None
        if year and month and day:
            try:
                valid_date = date(int(year), int(month), int(day))
            except ValueError:
                valid_date = None
        if level3_ok and year:
            self._ensure_year_option(year)
            self.year_var.set(year)
            self.handle_year_selection()
        if level3_ok and year and month:
            if month not in self.month_combo["values"]:
                self.month_combo["values"] = list(self.month_combo["values"]) + [month]
            self.month_var.set(month)
            self.handle_month_selection()
        if level3_ok and valid_date:
            target_day = f"{valid_date.day:02d}"
            self.day_var.set(target_day)
            self.handle_day_selection()

        self.is_public_card_var.set(bool(config.last_public_card))

    def _remember_state(self) -> None:
        def clean(value: str) -> Optional[str]:
            if value is None:
                return None
            stripped = value.strip()
            return stripped or None

        self.app_config.last_region = clean(self.region_var.get())
        self.app_config.last_level2 = clean(self.level2_var.get())
        self.app_config.last_level3 = clean(self.level3_var.get())
        self.app_config.last_year = clean(self.year_var.get())
        self.app_config.last_month = clean(self.month_var.get())
        self.app_config.last_day = clean(self.day_var.get())
        self.app_config.last_public_card = bool(self.is_public_card_var.get())

    def _persist_session_state(self) -> None:
        self._remember_state()
        self.save_config()

    def request_exit(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            self._persist_session_state()
        finally:
            self.destroy()

    def _refresh_comboboxes(self) -> None:
        self.level2_combo["values"] = self.app_config.level2_categories
        self.level3_combo["values"] = self.app_config.level3_categories
        if self.app_config.level2_categories:
            self.level2_var.set(self.app_config.level2_categories[0])
        if self.app_config.level3_categories:
            self.level3_var.set(self.app_config.level3_categories[0])

    def _populate_year_options(self) -> None:
        current_year = date.today().year
        start_year = max(2000, current_year - 10)
        end_year = current_year + 11
        years = [str(year) for year in range(start_year, end_year)]
        self.year_combo['values'] = years
        self.month_combo['values'] = [f"{month:02d}" for month in range(1, 13)]

    def _reset_date_controls(self) -> None:
        self.year_var.set("")
        self.month_var.set("")
        self.day_var.set("")
        self.day_combo['values'] = []
        self.current_date_path = None
        self.is_public_card_var.set(False)
        self._range_info = None
        self._range_end_date = None

    def handle_year_selection(self, event: Optional[tk.Event] = None) -> None:
        if not self.ensure_level3_path():
            self.year_var.set("")
            return
        self.current_date_path = None
        self._update_day_options()
        self._create_date_folder_if_ready()
        self._update_state()
        self._remember_state()

    def handle_month_selection(self, event: Optional[tk.Event] = None) -> None:
        if not self.ensure_level3_path():
            self.month_var.set("")
            return
        self.current_date_path = None
        self._update_day_options()
        self._create_date_folder_if_ready()
        self._update_state()
        self._remember_state()

    def handle_day_selection(self, event: Optional[tk.Event] = None) -> None:
        if not self.ensure_level3_path():
            self.day_var.set("")
            return
        self._create_date_folder_if_ready()
        self._update_state()
        self._remember_state()

    def _update_day_options(self) -> None:
        year = self.year_var.get()
        month = self.month_var.get()
        if not year or not month:
            self.day_combo['values'] = []
            self.day_var.set("")
            return
        try:
            year_int = int(year)
            month_int = int(month)
        except ValueError:
            self.day_combo['values'] = []
            self.day_var.set("")
            return
        days_in_month = calendar.monthrange(year_int, month_int)[1]
        options = [f"{day:02d}" for day in range(1, days_in_month + 1)]
        self.day_combo['values'] = options
        if self.day_var.get() not in options:
            self.day_var.set("")

    def _create_date_folder_if_ready(self) -> None:
        selected_date = self._get_selected_date()
        if not selected_date:
            return
        if not self.ensure_level3_path():
            return
        category_name = sanitize_folder_name(self.level3_var.get())
        if not category_name:
            return
        self._range_info = None
        self._range_end_date = None
        folder_name = f"{self._get_date_prefix(selected_date)}{category_name}"
        target = self.current_level3_path / folder_name
        target.mkdir(parents=True, exist_ok=True)
        self.current_date_path = target
        self.is_public_card_var.set(False)
        self.status_var.set(f"日期文件夹已就绪: {target}")
        self._update_state()

    def detect_document_date(self) -> None:
        if not self.ensure_level3_path():
            return
        if not self._has_api_credentials():
            messagebox.showwarning("提示", "请先在设置中配置识别接口或硅基流动信息")
            return
        if self._batch_running:
            messagebox.showinfo("提示", "批量识别正在进行中，请先停止或等待完成。", parent=self)
            return
        dialog_kwargs: Dict[str, Any] = {
            "parent": self,
            "title": "选择待识别的凭证文件",
            "filetypes": [("所有文件", "*.*")],
        }
        initial_dir = self._get_initial_dir("recognition")
        if initial_dir:
            dialog_kwargs["initialdir"] = initial_dir
        file_path = filedialog.askopenfilename(**dialog_kwargs)
        if not file_path:
            return
        document = Path(file_path)
        self.open_recognition_log()
        self._append_recognition_log(f"开始单文件识别: {document}")
        try:
            self._run_document_date_detection(document)
        finally:
            self._cleanup_debug_payload()

    def detect_document_folder_batch(self) -> None:
        if not self.ensure_level2_path():
            return
        if not self._has_api_credentials():
            messagebox.showwarning("提示", "请先在设置中配置识别接口或硅基流动信息")
            return
        if self._batch_running:
            messagebox.showinfo("提示", "批量识别正在进行中，请先停止或等待完成。", parent=self)
            return
        dialog_kwargs: Dict[str, Any] = {
            "parent": self,
            "title": "选择待识别的文件夹",
        }
        initial_dir = self._get_initial_dir("recognition")
        if initial_dir:
            dialog_kwargs["initialdir"] = initial_dir
        folder_selected = filedialog.askdirectory(**dialog_kwargs)
        if not folder_selected:
            return
        folder_path = Path(folder_selected)
        try:
            files = sorted(
                (
                    path
                    for path in folder_path.rglob("*")
                    if path.is_file()
                ),
                key=lambda path: (path.parent.relative_to(folder_path).as_posix(), path.name.lower()),
            )
        except OSError as exc:
            messagebox.showerror("错误", f"读取文件夹失败: {exc}", parent=self)
            return
        if not files:
            messagebox.showinfo("提示", "所选文件夹中没有可识别的文件", parent=self)
            return
        card_choice = messagebox.askyesnocancel(
            "批量公务卡选择",
            (
                "本次批量文件是否全部为公务卡交易？\n"
                "选择“是”则全部按公务卡保存；选择“否”则全部按非公务卡保存；取消以终止批量。"
            ),
            parent=self,
        )
        if card_choice is None:
            return
        all_public_card = bool(card_choice)

        self._batch_stop_requested = False
        self._batch_running = True
        self._batch_amount_stats = {}
        self._batch_files = files
        self._batch_total = len(files)
        self._batch_index = 0
        self._batch_success_count = 0
        self._batch_skipped_count = 0
        self._batch_stopped_early = False
        self._batch_public_card = all_public_card
        self._batch_saved_records = []
        self._batch_amount_only_pair_reports = []
        self._batch_ambiguous_pair_reports = []
        self._recognition_logs = []
        self.open_recognition_log()
        self._append_recognition_log(f"开始批量识别: {folder_path}，共 {len(files)} 个文件")
        self._append_recognition_log(
            "公务卡标记: " + ("全部按公务卡" if all_public_card else "全部按非公务卡")
        )
        self.status_var.set(f"开始批量识别，共 {len(files)} 个文件")
        self._update_state()
        self.after(0, self._process_next_batch_file)

    def _process_next_batch_file(self) -> None:
        if not self._batch_running:
            return
        if self._batch_stop_requested or self._closing:
            self._batch_stopped_early = True
            self.status_var.set(
                f"批量已停止，已处理 {self._batch_index} / {self._batch_total} 个文件"
            )
            self._append_recognition_log(
                f"批量停止: 已处理 {self._batch_index} / {self._batch_total} 个文件"
            )
            self._finish_batch_processing()
            return
        if self._batch_index >= self._batch_total:
            self._finish_batch_processing()
            return

        file_path = self._batch_files[self._batch_index]
        current_index = self._batch_index + 1
        self.status_var.set(
            f"批量识别 {current_index}/{self._batch_total}: {file_path.name}"
        )
        self._append_recognition_log(
            f"开始识别 {current_index}/{self._batch_total}: {file_path}"
        )
        worker = threading.Thread(
            target=self._recognize_batch_file_worker,
            args=(file_path, current_index),
            daemon=True,
        )
        worker.start()

    def _recognize_batch_file_worker(self, file_path: Path, index: int) -> None:
        payload: Optional[Mapping[str, Any]] = None
        error: Optional[BaseException] = None
        try:
            if not file_path.exists() or not file_path.is_file():
                raise FileNotFoundError(f"未找到可识别的文件: {file_path.name}")
            payload = self._recognize_document_payload(file_path)
        except BaseException as exc:  # Pass all worker failures back to Tk safely.
            error = exc
        try:
            self.after(
                0,
                lambda: self._handle_batch_file_result(file_path, index, payload, error),
            )
        except RuntimeError:
            return

    def _handle_batch_file_result(
        self,
        file_path: Path,
        index: int,
        payload: Optional[Mapping[str, Any]],
        error: Optional[BaseException],
    ) -> None:
        if not self._batch_running:
            return

        handled = False
        if error is not None:
            self.status_var.set(f"处理 {file_path.name} 出错: {error}")
            self._append_recognition_log(f"识别失败: {file_path.name}，错误: {error}")
        elif payload is not None:
            self._append_recognition_log(
                f"模型返回摘要: {file_path.name} -> {self._summarize_payload_for_log(payload)}"
            )
            try:
                handled = self._finish_document_date_detection(
                    file_path,
                    payload,
                    auto_confirm=True,
                    forced_public_card=self._batch_public_card,
                    auto_range=True,
                    allow_category_override=True,
                )
            except Exception as exc:
                self.status_var.set(f"处理 {file_path.name} 出错: {exc}")
                self._append_recognition_log(f"保存失败: {file_path.name}，错误: {exc}")

        if handled:
            self._batch_success_count += 1
            self._append_recognition_log(f"处理完成: {file_path.name}")
        else:
            self._batch_skipped_count += 1
            self._append_recognition_log(f"未保存/跳过: {file_path.name}")
        self._batch_index = max(self._batch_index, index)
        self.after(0, self._process_next_batch_file)

    def _finish_batch_processing(self) -> None:
        self._cleanup_debug_payload()
        if not self._batch_stopped_early and self._batch_index >= self._batch_total:
            self._pair_batch_saved_documents()
        self._batch_running = False
        self._batch_stop_requested = False
        self._update_state()

        summary_parts = [f"批量识别完成，成功 {self._batch_success_count} 个"]
        if self._batch_skipped_count:
            summary_parts.append(f"未保存 {self._batch_skipped_count} 个")
        if self._batch_stopped_early:
            summary_parts.append("已中途停止")
        if self._batch_amount_stats:
            kind_count = len(self._batch_amount_stats)
            amount_parts = [
                f"{name} {total:.2f}"
                for name, total in sorted(self._batch_amount_stats.items())
            ]
            summary_parts.append(f"发票类别数 {kind_count}")
            summary_parts.append("金额汇总: " + "；".join(amount_parts))
        if self._batch_amount_only_pair_reports:
            summary_parts.append(
                f"跨日期同金额配对 {len(self._batch_amount_only_pair_reports)} 组"
            )
        if self._batch_ambiguous_pair_reports:
            summary_parts.append(
                f"同金额待确认 {len(self._batch_ambiguous_pair_reports)} 组"
            )
        summary = "，".join(summary_parts)
        self.status_var.set(summary)
        self._append_recognition_log(summary)
        if self._batch_amount_only_pair_reports or self._batch_ambiguous_pair_reports:
            details: List[str] = []
            if self._batch_amount_only_pair_reports:
                details.append("跨日期同金额配对文件夹:")
                details.extend(self._batch_amount_only_pair_reports)
            if self._batch_ambiguous_pair_reports:
                if details:
                    details.append("")
                details.append("同金额多对多，需人工确认:")
                details.extend(self._batch_ambiguous_pair_reports)
            messagebox.showinfo("批量配对结果", "\n".join(details), parent=self)

    def _run_document_date_detection(
        self,
        document: Path,
        *,
        auto_confirm: bool = False,
        forced_public_card: Optional[bool] = None,
        auto_range: bool = False,
        allow_category_override: bool = False,
    ) -> bool:
        if not document.exists() or not document.is_file():
            if not auto_confirm:
                messagebox.showerror("错误", f"未找到可识别的文件: {document}", parent=self)
            else:
                self.status_var.set(f"未找到可识别的文件: {document.name}")
            self._append_recognition_log(f"文件不存在，跳过: {document}")
            return False
        status_prefix = f"识别日期中: {document.name}"
        self.status_var.set(status_prefix)
        self._append_recognition_log(status_prefix)
        self.update_idletasks()
        try:
            payload = self._recognize_document_payload(document)
            if not auto_confirm:
                self._append_recognition_log(
                    f"模型返回摘要: {document.name} -> {self._summarize_payload_for_log(payload)}"
                )
        except RecognitionAPIError as exc:
            if not auto_confirm:
                messagebox.showerror("识别失败", str(exc), parent=self)
            self.status_var.set(f"识别失败: {exc}")
            self._append_recognition_log(f"识别失败: {document.name}，错误: {exc}")
            return False
        except Exception as exc:
            if not auto_confirm:
                messagebox.showerror("识别失败", f"出现意外错误: {exc}", parent=self)
            self.status_var.set("识别失败，发生未知错误")
            self._append_recognition_log(f"识别失败: {document.name}，未知错误: {exc}")
            return False

        return self._finish_document_date_detection(
            document,
            payload,
            auto_confirm=auto_confirm,
            forced_public_card=forced_public_card,
            auto_range=auto_range,
            allow_category_override=allow_category_override,
        )

    def _recognize_document_payload(self, document: Path) -> Mapping[str, Any]:
        payload = call_recognition_api(
            endpoint=self.app_config.api_endpoint or "",
            app_id=self.app_config.api_app_id,
            app_secret=self.app_config.api_app_secret,
            file_path=document,
            token=self.app_config.api_token,
            data=self.app_config.api_extra_params,
            use_siliconflow=self.app_config.use_siliconflow,
            siliconflow_token=self.app_config.siliconflow_token,
            siliconflow_model=self.app_config.siliconflow_model,
            siliconflow_prompt=self.app_config.siliconflow_prompt,
        )
        self._write_debug_payload(payload)
        return payload

    def _finish_document_date_detection(
        self,
        document: Path,
        payload: Mapping[str, Any],
        *,
        auto_confirm: bool = False,
        forced_public_card: Optional[bool] = None,
        auto_range: bool = False,
        allow_category_override: bool = False,
    ) -> bool:
        detected_dt = extract_date_from_payload(payload)
        if not detected_dt:
            if not auto_confirm:
                messagebox.showwarning("提示", "未能在识别结果中提取日期信息")
            self.status_var.set("识别完成，但未找到日期信息")
            self._append_recognition_log(f"未提取到日期: {document.name}")
            return False
        detected_date = detected_dt.astimezone().date()

        category_override = None
        if allow_category_override:
            category_override = self._infer_invoice_category(payload, document)

        if not auto_confirm:
            confirm_date = messagebox.askyesnocancel(
                "确认识别日期",
                (
                    f"识别到的凭证日期为 {detected_date.strftime('%Y-%m-%d')}。\n"
                    "若日期无误请选择“是”以继续创建文件夹并保存；"
                    "若日期不正确请选择“否”，随后可更换模型或重新识别。"
                ),
                parent=self,
            )
            if confirm_date is None:
                self.status_var.set("已取消识别流程")
                self._append_recognition_log(f"用户取消确认日期: {document.name}")
                return False
            if not confirm_date:
                self.status_var.set(
                    "识别结果未确认，未创建文件夹。可调整模型后重新识别。"
                )
                self._append_recognition_log(f"用户否认识别日期: {document.name}")
                return False
        if auto_confirm:
            chosen_level3 = (
                self.level3_var.get()
                if (self.current_level3_path and self.level3_var.get())
                else None
            )
            target_category = category_override or chosen_level3 or DEFAULT_CATEGORY_FALLBACK
            if not self._ensure_level3_category(target_category, silent=True):
                self.status_var.set("自动创建类别失败，请检查类别名称")
                self._append_recognition_log(
                    f"自动创建类别失败: {document.name}，类别 {target_category}"
                )
                return False
            self._append_recognition_log(
                f"自动类别: {document.name} -> {target_category}"
            )
        self._apply_detected_date(detected_date)

        is_invoice, reason = self._infer_document_type(payload, document)
        doc_label = "发票" if is_invoice else "支付凭证"
        amount = self._extract_amount_from_payload(payload)
        amount_text = f"{amount:.2f}" if amount is not None else "未识别"
        self._append_recognition_log(
            f"识别结果: {document.name}，日期 {detected_date.isoformat()}，"
            f"类型 {doc_label}，金额 {amount_text}，依据 {reason or '无'}"
        )
        if auto_confirm and forced_public_card is not None:
            confirmation = forced_public_card
            self.is_public_card_var.set(confirmation)
            self._remember_state()
        else:
            confirmation = self._confirm_public_card(doc_label)
            if confirmation is None:
                self.status_var.set("已取消保存凭证")
                self._append_recognition_log(f"用户取消保存: {document.name}")
                return False
            self.is_public_card_var.set(confirmation)
            self._remember_state()

        try:
            saved_path = self._copy_document_to_current_date(
                document,
                is_invoice=is_invoice,
                mark_public_card=confirmation,
                document_date=detected_date,
                amount=amount,
                auto_range=auto_range,
            )
        except UserCancelledError:
            self.status_var.set("已取消保存凭证")
            self._append_recognition_log(f"保存取消: {document.name}")
            return False
        except Exception as exc:
            if not auto_confirm:
                messagebox.showwarning(
                    "提示",
                    f"日期识别成功，但保存文件失败: {exc}",
                    parent=self,
                )
            self.status_var.set(
                f"识别成功，日期为 {detected_date.isoformat()}，判定为{doc_label}"
            )
            self._append_recognition_log(f"保存失败: {document.name}，错误: {exc}")
            return False

        card_note = "(公务卡)" if confirmation else ""
        reason_note = f"，依据: {reason}" if reason else ""
        self.status_var.set(
            f"识别成功，日期为 {detected_date.isoformat()}，判定为{doc_label}{card_note}{reason_note}，已保存 {saved_path.name}"
        )
        self._append_recognition_log(f"已保存: {document.name} -> {saved_path}")
        if self._batch_running:
            self._record_batch_saved_document(
                saved_path=saved_path,
                is_invoice=is_invoice,
                document_date=detected_date,
                category=sanitize_folder_name(self.level3_var.get())
                or DEFAULT_CATEGORY_FALLBACK,
                amount=amount,
            )
        if amount is not None:
            card_amount_note = f"，金额 {amount:.2f}"
            self.status_var.set(self.status_var.get() + card_amount_note)
            if self._batch_running and is_invoice:
                target_category = sanitize_folder_name(self.level3_var.get()) or DEFAULT_CATEGORY_FALLBACK
                self._record_batch_invoice_amount(target_category, amount)
        return True

    def _update_drag_drop_hint(self, can_detect: bool) -> None:
        widget = getattr(self, "drag_drop_label", None)
        if widget is None:
            return
        if not self._drag_supported:
            widget.configure(text="当前环境暂不支持拖拽识别", foreground="gray")
            return
        if can_detect:
            widget.configure(text="将文件拖入此处识别日期", foreground="")
        else:
            widget.configure(
                text="拖拽识别需先完成地区/类别/日期选择并配置识别接口",
                foreground="gray",
            )

    def _handle_drop_for_recognition(self, event: tk.Event) -> str:
        widget = getattr(self, "drag_drop_label", None)
        if widget is not None:
            widget.configure(relief="ridge")
        files = self._extract_drop_files(getattr(event, "data", ""))
        if not files:
            self.status_var.set("未检测到可识别的文件")
            return "break"
        if len(files) > 1:
            messagebox.showinfo(
                "提示",
                "已检测到多个文件，仅对首个文件进行识别。",
                parent=self,
            )
        document = files[0]
        if not document.exists():
            messagebox.showwarning("提示", f"文件不存在: {document}", parent=self)
            return "break"
        if not self.ensure_level3_path():
            return "break"
        if not self._has_api_credentials():
            messagebox.showwarning("提示", "请先在设置中配置识别接口或硅基流动信息")
            return "break"
        confirm = messagebox.askyesno(
            "拖拽识别",
            f"检测到文件 {document.name}。\n是否立即进行日期识别？",
            parent=self,
        )
        if not confirm:
            self.status_var.set(f"已取消识别: {document.name}")
            return "break"
        self._run_document_date_detection(document)
        return "break"

    def _extract_drop_files(self, data: str) -> List[Path]:
        if not data:
            return []
        stripped = data.strip()
        if not stripped:
            return []
        try:
            parts = shlex.split(stripped, posix=False)
        except ValueError:
            cleaned = stripped.replace("{", "").replace("}", "")
            parts = cleaned.split()
        files: List[Path] = []
        for part in parts:
            candidate = part.strip("{}")
            if not candidate:
                continue
            files.append(Path(candidate))
        return files

    def _apply_detected_date(self, detected: date) -> None:
        year_str = str(detected.year)
        month_str = f"{detected.month:02d}"
        day_str = f"{detected.day:02d}"
        self._ensure_year_option(year_str)
        self.year_var.set(year_str)
        self.handle_year_selection()
        self.month_var.set(month_str)
        self.handle_month_selection()
        self.day_var.set(day_str)
        self.handle_day_selection()

    def _copy_document_to_current_date(
        self,
        source: Path,
        *,
        is_invoice: bool,
        mark_public_card: bool,
        document_date: Optional[date] = None,
        amount: Optional[float] = None,
        auto_range: bool = False,
    ) -> Path:
        if not self.ensure_date_path():
            raise RuntimeError("日期目录尚未就绪")
        if not self.current_date_path:
            raise RuntimeError("未找到日期目录")
        selected_date = self._get_selected_date()
        if not selected_date:
            raise RuntimeError("未选择有效日期")

        category_name = sanitize_folder_name(self.level3_var.get())
        if not category_name:
            raise RuntimeError("缺少二级类别名称")

        if auto_range:
            start_date = selected_date
            end_date = selected_date
            location_text = ""
        else:
            range_info = self._ensure_range_info(selected_date)
            if not range_info:
                raise UserCancelledError("用户取消了日期范围设置")
            start_date, end_date, location_text = range_info
        naming_date = document_date or selected_date
        date_part = naming_date.strftime("%Y%m%d")
        suffix_base = "发票" if is_invoice else "支付凭证"
        suffix = f"{suffix_base}(公务卡)" if mark_public_card else suffix_base
        amount_part = self._format_amount_for_filename(amount)
        stem = sanitize_folder_name(f"{date_part}{category_name}{amount_part}{suffix}")
        extension = "".join(source.suffixes)
        destination = self.current_date_path / f"{stem}{extension}"
        counter = 1
        while destination.exists():
            destination = self.current_date_path / f"{stem}{counter}{extension}"
            counter += 1
        shutil.copy2(source, destination)
        return destination

    @staticmethod
    def _format_amount_for_filename(amount: Optional[float]) -> str:
        if amount is None:
            return "未知金额"
        return f"{abs(amount):.2f}"

    def _record_batch_saved_document(
        self,
        *,
        saved_path: Path,
        is_invoice: bool,
        document_date: date,
        category: str,
        amount: Optional[float],
    ) -> None:
        self._batch_saved_records.append(
            {
                "path": saved_path,
                "folder": saved_path.parent,
                "is_invoice": is_invoice,
                "date": document_date,
                "category": category,
                "amount": amount,
            }
        )

    @staticmethod
    def _amount_pair_key(amount: Optional[float]) -> Optional[int]:
        if amount is None:
            return None
        return int(round(abs(amount) * 100))

    def _pair_batch_saved_documents(self) -> None:
        records = [
            record
            for record in self._batch_saved_records
            if self._amount_pair_key(record.get("amount")) is not None
        ]
        if not records:
            self._append_recognition_log("最终配对: 没有可用于配对的金额记录")
            return
        self._append_recognition_log("最终配对: 开始按日期+金额优先配对")

        matched: set[int] = set()
        invoice_records = [
            (index, record)
            for index, record in enumerate(records)
            if bool(record.get("is_invoice"))
        ]
        payment_records = [
            (index, record)
            for index, record in enumerate(records)
            if not bool(record.get("is_invoice"))
        ]

        def amount_key(record: Mapping[str, Any]) -> int:
            key = self._amount_pair_key(record.get("amount"))
            if key is None:
                raise ValueError("缺少金额")
            return key

        same_date_invoice_map: Dict[
            Tuple[date, int], List[Tuple[int, Dict[str, Any]]]
        ] = {}
        same_date_payment_map: Dict[
            Tuple[date, int], List[Tuple[int, Dict[str, Any]]]
        ] = {}
        for index, record in invoice_records:
            key = (record["date"], amount_key(record))
            same_date_invoice_map.setdefault(key, []).append((index, record))
        for index, record in payment_records:
            key = (record["date"], amount_key(record))
            same_date_payment_map.setdefault(key, []).append((index, record))

        for key, invoices in same_date_invoice_map.items():
            payments = same_date_payment_map.get(key, [])
            for invoice_item, payment_item in zip(invoices, payments):
                invoice_index, invoice = invoice_item
                payment_index, payment = payment_item
                if invoice_index in matched or payment_index in matched:
                    continue
                self._move_payment_record_to_invoice_folder(payment, invoice)
                matched.add(invoice_index)
                matched.add(payment_index)
                self._append_recognition_log(
                    (
                        "同日期同金额配对: "
                        f"{payment['path']} -> {invoice['folder']}"
                    )
                )

        unmatched_invoices: Dict[int, List[Tuple[int, Dict[str, Any]]]] = {}
        unmatched_payments: Dict[int, List[Tuple[int, Dict[str, Any]]]] = {}
        for index, record in invoice_records:
            if index not in matched:
                unmatched_invoices.setdefault(amount_key(record), []).append(
                    (index, record)
                )
        for index, record in payment_records:
            if index not in matched:
                unmatched_payments.setdefault(amount_key(record), []).append(
                    (index, record)
                )

        for amount_cents, invoices in sorted(unmatched_invoices.items()):
            payments = unmatched_payments.get(amount_cents, [])
            if not payments:
                continue
            amount_text = f"{amount_cents / 100:.2f}"
            if len(invoices) == 1 and len(payments) == 1:
                invoice_index, invoice = invoices[0]
                payment_index, payment = payments[0]
                invoice_folder = Path(invoice["folder"])
                payment_folder = Path(payment["folder"])
                self._move_payment_record_to_invoice_folder(payment, invoice)
                matched.add(invoice_index)
                matched.add(payment_index)
                self._batch_amount_only_pair_reports.append(
                    (
                        f"发票文件夹 {invoice_folder} <- 支付凭证文件夹 {payment_folder} | "
                        f"金额 {amount_text} | "
                        f"发票日期 {invoice['date'].isoformat()} / "
                        f"支付日期 {payment['date'].isoformat()}"
                    )
                )
                self._append_recognition_log(
                    (
                        "跨日期同金额配对: "
                        f"发票文件夹 {invoice_folder} <- 支付凭证文件夹 {payment_folder}，"
                        f"金额 {amount_text}"
                    )
                )
            else:
                invoice_folders = "；".join(
                    sorted({str(record["folder"]) for _, record in invoices})
                )
                payment_folders = "；".join(
                    sorted({str(record["folder"]) for _, record in payments})
                )
                self._batch_ambiguous_pair_reports.append(
                    (
                        f"金额 {amount_text}: 发票文件夹 {invoice_folders}；"
                        f"支付凭证文件夹 {payment_folders}"
                    )
                )
                self._append_recognition_log(
                    (
                        "同金额待确认: "
                        f"金额 {amount_text}，发票文件夹 {invoice_folders}；"
                        f"支付凭证文件夹 {payment_folders}"
                    )
                )

    def _move_payment_record_to_invoice_folder(
        self,
        payment: Dict[str, Any],
        invoice: Mapping[str, Any],
    ) -> None:
        payment_path = Path(payment["path"])
        invoice_folder = Path(invoice["folder"])
        if payment_path.parent == invoice_folder:
            return
        if not payment_path.exists():
            return
        invoice_folder.mkdir(parents=True, exist_ok=True)
        destination = self._unique_destination(invoice_folder, payment_path.name)
        shutil.move(str(payment_path), str(destination))
        payment["path"] = destination
        payment["folder"] = invoice_folder

    @staticmethod
    def _unique_destination(folder: Path, filename: str) -> Path:
        destination = folder / filename
        if not destination.exists():
            return destination
        source_name = Path(filename)
        stem = source_name.stem
        suffix = "".join(source_name.suffixes)
        counter = 1
        while True:
            candidate = folder / f"{stem}{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _get_initial_dir(self, kind: str) -> Optional[str]:
        mapping = {
            "invoice": self.app_config.invoice_source_dir,
            "payment": self.app_config.payment_source_dir,
            "recognition": self.app_config.recognition_source_dir,
        }
        target = mapping.get(kind)
        if not target:
            return None
        try:
            resolved = Path(target).expanduser()
        except OSError:
            return None
        if resolved.is_dir():
            return str(resolved)
        return None

    def _confirm_public_card(self, doc_label: str) -> Optional[bool]:
        current = self.is_public_card_var.get()
        current_text = "当前标记: 公务卡" if current else "当前标记: 非公务卡"
        response = messagebox.askyesnocancel(
            "确认公务卡状态",
            f"此次{doc_label}是否为公务卡交易？\n{current_text}\n选择“是”将名称增加(公务卡)。",
            parent=self,
        )
        if response is None:
            return None
        return bool(response)

    def _infer_document_type(
        self, payload: Mapping[str, Any], source: Path
    ) -> Tuple[bool, str]:
        model_type = self._extract_model_document_type(payload)
        if model_type is not None:
            is_invoice, evidence = model_type
            return is_invoice, evidence

        invoice_score = 0
        payment_score = 0
        invoice_hits: List[str] = []
        payment_hits: List[str] = []

        def register_hit(is_invoice: bool, keyword: str, weight: int) -> None:
            nonlocal invoice_score, payment_score
            if is_invoice:
                invoice_score += weight
                if keyword not in invoice_hits:
                    invoice_hits.append(keyword)
            else:
                payment_score += weight
                if keyword not in payment_hits:
                    payment_hits.append(keyword)

        def process_text(text: str, base_weight: int = 1) -> None:
            if not text:
                return
            lowered = text.lower()
            for keyword, weight in INVOICE_TEXT_HINTS:
                lowered_kw = keyword.lower()
                if keyword in text or lowered_kw in lowered:
                    register_hit(True, keyword, weight * base_weight)
            for keyword, weight in PAYMENT_TEXT_HINTS:
                lowered_kw = keyword.lower()
                if keyword in text or lowered_kw in lowered:
                    register_hit(False, keyword, weight * base_weight)

        def walk(obj: Any) -> None:
            if isinstance(obj, Mapping):
                for key, value in obj.items():
                    key_text = str(key)
                    process_text(key_text, base_weight=2)
                    walk(value)
            elif isinstance(obj, str):
                process_text(obj)
            elif isinstance(obj, Iterable) and not isinstance(obj, (bytes, bytearray)):
                for item in obj:
                    walk(item)

        if isinstance(payload, Mapping):
            walk(payload)

        if invoice_score > payment_score:
            reason = "、".join(invoice_hits[:4])
            return True, reason
        if payment_score > invoice_score:
            reason = "、".join(payment_hits[:4])
            return False, reason

        if invoice_score == 0 and payment_score == 0:
            return True, "正文未命中明显类型关键词，默认按发票处理"
        combined_invoice = "、".join(invoice_hits[:3]) if invoice_hits else "无"
        combined_payment = "、".join(payment_hits[:3]) if payment_hits else "无"
        reason = f"发票特征({combined_invoice}) vs 支付特征({combined_payment})"
        return True, reason

    @staticmethod
    def _extract_model_document_type(
        payload: Mapping[str, Any],
    ) -> Optional[Tuple[bool, str]]:
        def normalize(value: Any) -> str:
            return str(value).strip().lower().replace("-", "_").replace(" ", "_")

        def classify(value: Any) -> Optional[Tuple[bool, str]]:
            normalized = normalize(value)
            if not normalized:
                return None
            invoice_values = {normalize(item) for item in INVOICE_DOCUMENT_TYPE_VALUES}
            payment_values = {normalize(item) for item in PAYMENT_DOCUMENT_TYPE_VALUES}
            if normalized in invoice_values:
                return True, f"模型返回document_type={value}"
            if normalized in payment_values:
                return False, f"模型返回document_type={value}"
            if "invoice" in normalized or "发票" in normalized:
                return True, f"模型返回document_type={value}"
            if (
                "payment" in normalized
                or "pay_record" in normalized
                or "支付" in normalized
                or "付款" in normalized
                or "转账" in normalized
            ):
                return False, f"模型返回document_type={value}"
            return None

        def inspect_mapping(mapping: Mapping[str, Any]) -> Optional[Tuple[bool, str]]:
            for key in DOCUMENT_TYPE_KEYS:
                if key in mapping:
                    result = classify(mapping[key])
                    if result:
                        return result
            is_invoice = mapping.get("is_invoice")
            if isinstance(is_invoice, bool):
                return is_invoice, f"模型返回is_invoice={is_invoice}"
            return None

        parsed = payload.get("parsed")
        if isinstance(parsed, Mapping):
            result = inspect_mapping(parsed)
            if result:
                return result
        return inspect_mapping(payload)

    def _infer_invoice_category(
        self, payload: Mapping[str, Any], source: Path
    ) -> Optional[str]:
        """Use the model返回的category字段，不做本地猜测。"""

        if not isinstance(payload, Mapping):
            return None

        def pick_category(mapping: Mapping[str, Any]) -> Optional[str]:
            value = mapping.get("category")
            if isinstance(value, str):
                cleaned = value.strip()
                return cleaned or None
            return None

        parsed = payload.get("parsed")
        if isinstance(parsed, Mapping):
            cat = pick_category(parsed)
            if cat:
                return cat

        cat = pick_category(payload)
        if cat:
            return cat

        return None

    def _ensure_level3_category(self, name: str, silent: bool = False) -> bool:
        if not self.ensure_category_path():
            return False
        clean_name = sanitize_folder_name(name)
        if not clean_name:
            if not silent:
                messagebox.showwarning("提示", "类别名称非法")
            return False
        if not is_valid_folder_name(clean_name):
            if not silent:
                messagebox.showwarning("提示", "类别名称包含非法字符")
            return False
        added = self.app_config.add_level3_category(clean_name)
        if added:
            self.save_config()
            self._refresh_comboboxes()
        self.level3_var.set(clean_name)
        self.handle_level3_selection()
        return True

    def _parse_amount_text(self, text: str) -> Optional[float]:
        if not text:
            return None
        for match in _AMOUNT_PATTERN.finditer(text):
            candidate = match.group().replace(",", "")
            try:
                return float(candidate)
            except ValueError:
                continue
        return None

    def _extract_amount_from_payload(self, payload: Mapping[str, Any]) -> Optional[float]:
        best: Tuple[int, float] | None = None

        def consider(value: Any, weight: int) -> None:
            nonlocal best
            parsed = None
            if isinstance(value, (int, float)):
                parsed = float(value)
            elif isinstance(value, str):
                parsed = self._parse_amount_text(value)
            if parsed is None:
                return
            if best is None or weight > best[0]:
                best = (weight, parsed)

        def walk(obj: Any, weight: int = 1) -> None:
            if obj is None:
                return
            if isinstance(obj, Mapping):
                for key, value in obj.items():
                    key_text = str(key)
                    key_weight = weight + 1 if any(k in key_text for k in AMOUNT_KEYWORDS) else weight
                    walk(value, key_weight)
                return
            if isinstance(obj, str):
                consider(obj, weight)
                return
            if isinstance(obj, (int, float)):
                consider(obj, weight)
                return
            if isinstance(obj, Iterable) and not isinstance(obj, (bytes, bytearray)):
                for item in obj:
                    walk(item, weight)

        walk(payload, 1)
        if best is None:
            return None
        return best[1]

    def _record_batch_invoice_amount(self, category: str, amount: float) -> None:
        cleaned = sanitize_folder_name(category) or DEFAULT_CATEGORY_FALLBACK
        current = self._batch_amount_stats.get(cleaned, 0.0)
        self._batch_amount_stats[cleaned] = current + amount

    def _write_debug_payload(self, payload: Mapping[str, Any]) -> None:
        try:
            self._debug_payload_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            # Debug写入失败不影响主流程
            pass

    def _cleanup_debug_payload(self) -> None:
        try:
            if self._debug_payload_path.exists():
                self._debug_payload_path.unlink()
        except OSError:
            pass

    def _ensure_year_option(self, year: str) -> None:
        current_values = list(self.year_combo["values"])
        if year in current_values:
            return
        try:
            normalized = {int(value) for value in current_values}
            normalized.add(int(year))
            ordered = sorted(normalized)
            self.year_combo["values"] = [str(value) for value in ordered]
        except ValueError:
            current_values.append(year)
            self.year_combo["values"] = current_values

    def _has_api_credentials(self) -> bool:
        if self.app_config.use_siliconflow:
            return bool(self.app_config.siliconflow_token)
        has_signed = (
            self.app_config.api_app_id
            and self.app_config.api_app_secret
            and self.app_config.api_endpoint
        )
        has_token = self.app_config.api_token and self.app_config.api_endpoint
        return bool(has_signed or has_token)

    def _get_selected_date(self) -> Optional[date]:
        year = self.year_var.get()
        month = self.month_var.get()
        day = self.day_var.get()
        if not (year and month and day):
            return None
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            messagebox.showwarning("提示", "请选择有效的日期")
            return None

    def _get_date_prefix(self, selected: date) -> str:
        return selected.strftime("%y%m%d")

    def _ensure_range_info(self, end_date: date) -> Optional[Tuple[date, date, str]]:
        if self._range_info and self._range_end_date == end_date:
            return self._range_info
        info = self._prompt_date_range_info(end_date)
        if info is None:
            return None
        self._range_end_date = end_date
        self._range_info = info
        return info

    def _prompt_date_range_info(self, end_date: date) -> Optional[Tuple[date, date, str]]:
        response = messagebox.askyesnocancel(
            "日期范围确认",
            (
                "当前凭证是否跨越多天？\n"
                "选择“是”后请输入需要向前回溯的天数，例如输入 3 将生成从"
                f" {end_date.strftime('%Y-%m-%d')} 向前推 3 天到当日的区间。"
            ),
            parent=self,
        )
        if response is None:
            return None
        start_date = end_date
        if response:
            while True:
                days_text = ask_text(
                    self,
                    "跨天天数",
                    "请输入需要向前回溯的天数 (正整数):",
                )
                if days_text is None:
                    return None
                days_text = days_text.strip()
                if not days_text:
                    messagebox.showwarning("提示", "天数不能为空，请重新输入。", parent=self)
                    continue
                try:
                    days_value = int(days_text)
                except ValueError:
                    messagebox.showwarning("提示", "请输入有效的数字。", parent=self)
                    continue
                if days_value < 1:
                    messagebox.showwarning("提示", "天数需为正整数。", parent=self)
                    continue
                start_date = end_date - timedelta(days=days_value)
                break
        location_text = ask_text(
            self,
            "地点信息",
            "请输入地点 (可留空):",
        )
        location_clean = sanitize_folder_name(location_text) if location_text else ""
        return (start_date, end_date, location_clean)

    def _format_date_range_prefix(self, start: date, end: date) -> str:
        if start > end:
            start, end = end, start
        start_str = start.strftime("%y%m%d")
        end_str = end.strftime("%y%m%d")
        if start == end:
            return end_str
        return f"{start_str}-{end_str}"

    def upload_invoice(self) -> None:
        self._handle_file_upload(is_invoice=True)

    def upload_payment_proof(self) -> None:
        self._handle_file_upload(is_invoice=False)

    def _handle_file_upload(self, *, is_invoice: bool) -> None:
        if not self.ensure_date_path():
            return
        filetypes = [("所有文件", "*.*")]
        title = "选择发票文件" if is_invoice else "选择支付凭证文件"
        dialog_kwargs: Dict[str, Any] = {
            "parent": self,
            "title": title,
            "filetypes": filetypes,
        }
        initial_dir = self._get_initial_dir("invoice" if is_invoice else "payment")
        if initial_dir:
            dialog_kwargs["initialdir"] = initial_dir
        source_path = filedialog.askopenfilename(**dialog_kwargs)
        if not source_path:
            return
        source = Path(source_path)
        if not source.exists():
            messagebox.showerror("错误", "选择的文件不存在")
            return
        selected_date = self._get_selected_date()
        if not selected_date:
            return
        try:
            destination = self._copy_document_to_current_date(
                source,
                is_invoice=is_invoice,
                mark_public_card=self.is_public_card_var.get(),
            )
        except UserCancelledError:
            self.status_var.set("已取消保存凭证")
            return
        except Exception as exc:
            messagebox.showerror("错误", f"保存文件失败: {exc}")
            return
        self.status_var.set(f"已保存文件: {destination}")

    def _update_state(self) -> None:
        has_root = bool(self.app_config.root_path)
        region_state = "readonly" if has_root else "disabled"
        self.region_combo.configure(state=region_state)
        self.level2_combo.configure(state=region_state)
        self.level3_combo.configure(state=region_state)

        can_select_date = self.current_level3_path is not None
        date_state = "readonly" if can_select_date else "disabled"
        for combo in (self.year_combo, self.month_combo, self.day_combo):
            combo.configure(state=date_state)
        if not can_select_date:
            self.is_public_card_var.set(False)

        can_upload = self.current_date_path is not None and not self._batch_running
        can_detect_date = (
            can_select_date and self._has_api_credentials() and not self._batch_running
        )
        can_batch = (
            self.current_category_path is not None
            and self._has_api_credentials()
            and not self._batch_running
        )
        self.detect_date_btn.configure(state="normal" if can_detect_date else "disabled")
        self.batch_detect_btn.configure(state="normal" if can_batch else "disabled")
        self._update_drag_drop_hint(can_detect_date)
        self.public_card_check.configure(
            state="normal" if (can_select_date and not self._batch_running) else "disabled"
        )
        self.upload_invoice_btn.configure(state="normal" if can_upload else "disabled")
        self.upload_payment_btn.configure(state="normal" if can_upload else "disabled")
        stop_state = "normal" if self._batch_running else "disabled"
        if hasattr(self, "stop_batch_btn"):
            self.stop_batch_btn.configure(state=stop_state)

    def request_stop_batch(self) -> None:
        if not self._batch_running:
            return
        self._batch_stop_requested = True
        self.status_var.set("已请求停止批量，当前文件处理完成后停止")
        self._append_recognition_log("收到停止批量请求，当前文件处理完成后停止")

    def get_root_path_display(self) -> str:
        return self.app_config.root_path or "未设置"

    def open_settings(self) -> None:
        SettingsWindow(self)

    def set_root_path(self, new_path: str) -> None:
        sanitized = new_path.strip()
        if not sanitized:
            return
        path_obj = Path(sanitized)
        try:
            path_obj.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("错误", f"无法创建根目录: {exc}")
            return
        self.app_config.root_path = str(path_obj)
        self.current_region_path = None
        self.current_category_path = None
        self.current_level3_path = None
        self._reset_date_controls()
        self.root_path_var.set(self.get_root_path_display())
        self._update_state()
        self._remember_state()
        self.save_config()
        self.status_var.set(f"根目录已更新: {path_obj}")

    def handle_region_selection(self, event: Optional[tk.Event] = None) -> None:
        if not self.ensure_root_path():
            return
        region = sanitize_folder_name(self.region_var.get())
        if not region:
            return
        target = Path(self.app_config.root_path) / region
        target.mkdir(parents=True, exist_ok=True)
        self.current_region_path = target
        self.current_category_path = None
        self.current_level3_path = None
        self._reset_date_controls()
        self._update_state()
        self.status_var.set(f"地区文件夹已就绪: {target}")
        self._remember_state()

    def handle_level2_selection(self, event: Optional[tk.Event] = None) -> None:
        if not self.ensure_region_path():
            return
        category = sanitize_folder_name(self.level2_var.get())
        if not category:
            return
        target = self.current_region_path / category
        target.mkdir(parents=True, exist_ok=True)
        self.current_category_path = target
        self.current_level3_path = None
        self._reset_date_controls()
        self._update_state()
        self.status_var.set(f"一级类别文件夹已就绪: {target}")
        self._remember_state()

    def handle_level3_selection(self, event: Optional[tk.Event] = None) -> None:
        if not self.ensure_category_path():
            return
        sub_category = sanitize_folder_name(self.level3_var.get())
        if not sub_category:
            return
        target = self.current_category_path / sub_category
        target.mkdir(parents=True, exist_ok=True)
        self.current_level3_path = target
        self._reset_date_controls()
        self._update_state()
        self.status_var.set(f"二级类别文件夹已就绪: {target}")
        self._remember_state()

    def ensure_root_path(self) -> bool:
        if not self.app_config.root_path:
            messagebox.showwarning("提示", "请先在设置中选择根目录")
            return False
        return True

    def ensure_region_path(self) -> bool:
        if not self.ensure_root_path():
            return False
        if not self.current_region_path:
            messagebox.showwarning("提示", "请先选择地区")
            return False
        return True

    def ensure_level2_path(self) -> bool:
        # 兼容批量识别无需预选二级类别时的校验
        return self.ensure_category_path()

    def ensure_category_path(self) -> bool:
        if not self.ensure_region_path():
            return False
        if not self.current_category_path:
            messagebox.showwarning("提示", "请先选择一级类别")
            return False
        return True

    def ensure_level3_path(self) -> bool:
        if not self.ensure_category_path():
            return False
        if not self.current_level3_path:
            messagebox.showwarning("提示", "请先选择二级类别")
            return False
        return True

    def ensure_date_path(self) -> bool:
        if not self.ensure_level3_path():
            return False
        if not self.current_date_path:
            messagebox.showwarning("提示", "请先选择日期")
            return False
        return True

    def add_level2_category(self) -> None:
        new_name = ask_text(self, "新增类别", "请输入新的一级类别名称:")
        if not new_name:
            return
        clean_name = sanitize_folder_name(new_name)
        if not clean_name:
            messagebox.showwarning("提示", "类别名称非法")
            return
        if not is_valid_folder_name(clean_name):
            messagebox.showwarning("提示", "类别名称包含非法字符")
            return
        if not self.app_config.add_level2_category(clean_name):
            messagebox.showinfo("提示", "该类别已存在")
            return
        self.save_config()
        self._refresh_comboboxes()
        self.level2_var.set(clean_name)
        self.status_var.set(f"新增一级类别: {clean_name}")
        self._remember_state()

    def add_level3_category(self) -> None:
        new_name = ask_text(self, "新增类别", "请输入新的二级类别名称:")
        if not new_name:
            return
        clean_name = sanitize_folder_name(new_name)
        if not clean_name:
            messagebox.showwarning("提示", "类别名称非法")
            return
        if not is_valid_folder_name(clean_name):
            messagebox.showwarning("提示", "类别名称包含非法字符")
            return
        if not self.app_config.add_level3_category(clean_name):
            messagebox.showinfo("提示", "该类别已存在")
            return
        self.save_config()
        self._refresh_comboboxes()
        self.level3_var.set(clean_name)
        self.status_var.set(f"新增二级类别: {clean_name}")
        self._remember_state()

    def save_config(self) -> None:
        try:
            self.app_config.ensure_defaults()
            self.config_manager.save(self.password, self.app_config)
        except EncryptionError as exc:
            messagebox.showerror("错误", f"保存配置失败: {exc}")

    def update_password(self, old_password: str, new_password: str) -> None:
        self.config_manager.update_password(old_password, new_password, self.app_config)
        self.password = new_password


def run_app(config_manager: ConfigManager, config: AppConfig, password: str) -> None:
    window = MainWindow(config_manager=config_manager, config=config, password=password)
    window.mainloop()
