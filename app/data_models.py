from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .constants import (
    DEFAULT_INVOICE_SOURCE_DIR,
    DEFAULT_LEVEL2_CATEGORIES,
    DEFAULT_LEVEL3_CATEGORIES,
    DEFAULT_PAYMENT_SOURCE_DIR,
    DEFAULT_RECOGNITION_SOURCE_DIR,
)


def _unique_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


@dataclass
class AppConfig:
    root_path: str | None = None
    level2_categories: List[str] = field(
        default_factory=lambda: DEFAULT_LEVEL2_CATEGORIES.copy()
    )
    level3_categories: List[str] = field(
        default_factory=lambda: DEFAULT_LEVEL3_CATEGORIES.copy()
    )
    api_app_id: str | None = None
    api_app_secret: str | None = None
    api_endpoint: str | None = None
    api_token: str | None = None
    api_extra_params: Dict[str, str] = field(default_factory=dict)
    use_siliconflow: bool = False
    siliconflow_token: str | None = None
    siliconflow_model: str = "Qwen/Qwen3-VL-32B-Instruct"
    siliconflow_prompt: str | None = None
    invoice_source_dir: str | None = DEFAULT_INVOICE_SOURCE_DIR
    payment_source_dir: str | None = DEFAULT_PAYMENT_SOURCE_DIR
    recognition_source_dir: str | None = DEFAULT_RECOGNITION_SOURCE_DIR
    siliconflow_model_history: List[str] = field(default_factory=list)
    last_region: str | None = None
    last_level2: str | None = None
    last_level3: str | None = None
    last_year: str | None = None
    last_month: str | None = None
    last_day: str | None = None
    last_public_card: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        root_path = data.get("root_path")
        level2 = data.get("level2_categories") or []
        level3 = data.get("level3_categories") or []
        api_app_id = data.get("api_app_id")
        api_app_secret = data.get("api_app_secret")
        api_endpoint = data.get("api_endpoint")
        api_token = data.get("api_token")
        raw_extra = data.get("api_extra_params") or {}
        use_siliconflow = bool(data.get("use_siliconflow", False))
        siliconflow_token = data.get("siliconflow_token")
        siliconflow_model = data.get("siliconflow_model") or "Qwen/Qwen2.5-VL-72B-Instruct"
        siliconflow_prompt = data.get("siliconflow_prompt")
        invoice_source_dir = data.get("invoice_source_dir") or DEFAULT_INVOICE_SOURCE_DIR
        payment_source_dir = data.get("payment_source_dir") or DEFAULT_PAYMENT_SOURCE_DIR
        recognition_source_dir = (
            data.get("recognition_source_dir") or DEFAULT_RECOGNITION_SOURCE_DIR
        )
        raw_model_history = data.get("siliconflow_model_history") or []
        last_region = data.get("last_region")
        last_level2 = data.get("last_level2")
        last_level3 = data.get("last_level3")
        last_year = data.get("last_year")
        last_month = data.get("last_month")
        last_day = data.get("last_day")
        last_public_card = bool(data.get("last_public_card", False))
        if not isinstance(raw_extra, dict):
            raw_extra = {}
        extra_params = {str(key): str(value) for key, value in raw_extra.items()}
        if not isinstance(raw_model_history, list):
            raw_model_history = []
        model_history = [
            str(item).strip()
            for item in raw_model_history
            if isinstance(item, (str, int, float)) and str(item).strip()
        ]
        instance = cls(
            root_path=root_path,
            level2_categories=_unique_preserve_order(level2 or DEFAULT_LEVEL2_CATEGORIES),
            level3_categories=_unique_preserve_order(level3 or DEFAULT_LEVEL3_CATEGORIES),
            api_app_id=api_app_id,
            api_app_secret=api_app_secret,
            api_endpoint=api_endpoint,
            api_token=api_token,
            api_extra_params=extra_params,
            use_siliconflow=use_siliconflow,
            siliconflow_token=siliconflow_token,
            siliconflow_model=siliconflow_model,
            siliconflow_prompt=siliconflow_prompt,
            invoice_source_dir=invoice_source_dir,
            payment_source_dir=payment_source_dir,
            recognition_source_dir=recognition_source_dir,
            siliconflow_model_history=model_history,
            last_region=str(last_region).strip() if last_region else None,
            last_level2=str(last_level2).strip() if last_level2 else None,
            last_level3=str(last_level3).strip() if last_level3 else None,
            last_year=str(last_year).strip() if last_year else None,
            last_month=str(last_month).strip() if last_month else None,
            last_day=str(last_day).strip() if last_day else None,
            last_public_card=last_public_card,
        )
        instance.ensure_defaults()
        return instance

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root_path": self.root_path,
            "level2_categories": self.level2_categories,
            "level3_categories": self.level3_categories,
            "api_app_id": self.api_app_id,
            "api_app_secret": self.api_app_secret,
            "api_endpoint": self.api_endpoint,
            "api_token": self.api_token,
            "api_extra_params": self.api_extra_params,
            "use_siliconflow": self.use_siliconflow,
            "siliconflow_token": self.siliconflow_token,
            "siliconflow_model": self.siliconflow_model,
            "siliconflow_prompt": self.siliconflow_prompt,
            "invoice_source_dir": self.invoice_source_dir,
            "payment_source_dir": self.payment_source_dir,
            "recognition_source_dir": self.recognition_source_dir,
            "siliconflow_model_history": self.siliconflow_model_history,
            "last_region": self.last_region,
            "last_level2": self.last_level2,
            "last_level3": self.last_level3,
            "last_year": self.last_year,
            "last_month": self.last_month,
            "last_day": self.last_day,
            "last_public_card": self.last_public_card,
        }

    def ensure_defaults(self) -> None:
        """Ensure mandatory defaults are present while keeping user-defined order."""
        for default in DEFAULT_LEVEL2_CATEGORIES:
            if default not in self.level2_categories:
                self.level2_categories.insert(0, default)
        for default in DEFAULT_LEVEL3_CATEGORIES:
            if default not in self.level3_categories:
                self.level3_categories.insert(0, default)
        self.level2_categories = _unique_preserve_order(self.level2_categories)
        self.level3_categories = _unique_preserve_order(self.level3_categories)
        if not self.invoice_source_dir:
            self.invoice_source_dir = DEFAULT_INVOICE_SOURCE_DIR
        if not self.payment_source_dir:
            self.payment_source_dir = DEFAULT_PAYMENT_SOURCE_DIR
        if not self.recognition_source_dir:
            self.recognition_source_dir = DEFAULT_RECOGNITION_SOURCE_DIR
        if self.siliconflow_model not in self.siliconflow_model_history:
            self.siliconflow_model_history.append(self.siliconflow_model)
        defaults = {"Qwen/Qwen2.5-VL-72B-Instruct", "Qwen/Qwen3-VL-32B-Instruct"}
        for item in defaults:
            if item not in self.siliconflow_model_history:
                self.siliconflow_model_history.insert(0, item)
        self.siliconflow_model_history = _unique_preserve_order(self.siliconflow_model_history)

    def add_level2_category(self, name: str) -> bool:
        name = name.strip()
        if not name or name in self.level2_categories:
            return False
        self.level2_categories.append(name)
        return True

    def add_level3_category(self, name: str) -> bool:
        name = name.strip()
        if not name or name in self.level3_categories:
            return False
        self.level3_categories.append(name)
        return True

    def add_siliconflow_model(self, model: str) -> None:
        normalized = model.strip()
        if not normalized:
            return
        if normalized not in self.siliconflow_model_history:
            self.siliconflow_model_history.append(normalized)
