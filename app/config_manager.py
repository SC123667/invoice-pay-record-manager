from __future__ import annotations

from pathlib import Path
from typing import Optional

from .constants import CONFIG_FILE
from .data_models import AppConfig
from .encryption import EncryptionError, SimpleEncryption


class ConfigManager:
    """Handles persistence of application configuration with encryption."""

    def __init__(self, config_path: Path | None = None, encryption: SimpleEncryption | None = None) -> None:
        self.config_path = config_path or CONFIG_FILE
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.encryption = encryption or SimpleEncryption()

    def load(self, password: str) -> AppConfig:
        if not self.config_path.exists():
            return AppConfig()
        raw = self.config_path.read_text(encoding="utf-8")
        payload = self.encryption.deserialize(raw)
        data = self.encryption.decrypt(password, payload)
        return AppConfig.from_dict(_json_load(data))

    def save(self, password: str, config: AppConfig) -> None:
        serialized = _json_dump(config.to_dict()).encode("utf-8")
        payload = self.encryption.encrypt(password, serialized)
        self.config_path.write_text(self.encryption.serialize(payload), encoding="utf-8")

    def update_password(self, current_password: str, new_password: str, config: AppConfig) -> None:
        if not new_password:
            raise EncryptionError("新密码不能为空")
        if self.config_path.exists():
            # Validate current password before re-encrypting
            self.load(current_password)
        serialized = _json_dump(config.to_dict()).encode("utf-8")
        payload = self.encryption.encrypt(new_password, serialized)
        self.config_path.write_text(self.encryption.serialize(payload), encoding="utf-8")


def _json_dump(data: dict) -> str:
    import json

    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def _json_load(raw: bytes) -> dict:
    import json

    return json.loads(raw.decode("utf-8"))
