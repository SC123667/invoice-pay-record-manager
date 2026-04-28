from __future__ import annotations

import base64
import hmac
import json
import secrets
from dataclasses import dataclass
from hashlib import pbkdf2_hmac, sha256
from typing import Any, Dict


class EncryptionError(Exception):
    """Raised when encrypted payload cannot be decrypted or authenticated."""


@dataclass
class EncryptedPayload:
    salt: bytes
    iv: bytes
    ciphertext: bytes
    mac: bytes
    iterations: int

    def to_serializable(self) -> Dict[str, Any]:
        return {
            "salt": base64.b64encode(self.salt).decode("ascii"),
            "iv": base64.b64encode(self.iv).decode("ascii"),
            "ciphertext": base64.b64encode(self.ciphertext).decode("ascii"),
            "mac": base64.b64encode(self.mac).decode("ascii"),
            "iterations": self.iterations,
        }

    @classmethod
    def from_raw(cls, data: Dict[str, Any]) -> "EncryptedPayload":
        try:
            salt = base64.b64decode(data["salt"])
            iv = base64.b64decode(data["iv"])
            ciphertext = base64.b64decode(data["ciphertext"])
            mac = base64.b64decode(data["mac"])
            iterations = int(data.get("iterations", 200_000))
        except Exception as exc:  # noqa: BLE001 - want broad catch to wrap into EncryptionError
            raise EncryptionError("无效的加密数据格式") from exc
        return cls(salt=salt, iv=iv, ciphertext=ciphertext, mac=mac, iterations=iterations)


class SimpleEncryption:
    """Lightweight password-based encryption with HMAC integrity."""

    def __init__(self, iterations: int = 200_000) -> None:
        self.iterations = iterations

    def encrypt(self, password: str, data: bytes) -> EncryptedPayload:
        if not password:
            raise EncryptionError("密码不能为空")
        salt = secrets.token_bytes(16)
        key = self._derive_key(password, salt, self.iterations)
        iv = secrets.token_bytes(16)
        ciphertext = self._xor_stream(key, iv, data)
        mac = self._hmac(key, iv + ciphertext)
        return EncryptedPayload(salt=salt, iv=iv, ciphertext=ciphertext, mac=mac, iterations=self.iterations)

    def decrypt(self, password: str, payload: EncryptedPayload) -> bytes:
        if not password:
            raise EncryptionError("密码不能为空")
        key = self._derive_key(password, payload.salt, payload.iterations)
        expected_mac = self._hmac(key, payload.iv + payload.ciphertext)
        if not hmac.compare_digest(expected_mac, payload.mac):
            raise EncryptionError("密码错误或数据已损坏")
        return self._xor_stream(key, payload.iv, payload.ciphertext)

    @staticmethod
    def _derive_key(password: str, salt: bytes, iterations: int) -> bytes:
        return pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)

    @staticmethod
    def _xor_stream(key: bytes, iv: bytes, data: bytes) -> bytes:
        keystream = bytearray()
        counter = 0
        while len(keystream) < len(data):
            counter_bytes = counter.to_bytes(4, "big")
            block = sha256(key + iv + counter_bytes).digest()
            keystream.extend(block)
            counter += 1
        return bytes(a ^ b for a, b in zip(data, keystream))

    @staticmethod
    def _hmac(key: bytes, data: bytes) -> bytes:
        mac_key = sha256(key + b"hmac").digest()
        return hmac.new(mac_key, data, sha256).digest()

    @staticmethod
    def serialize(payload: EncryptedPayload) -> str:
        return json.dumps(payload.to_serializable(), ensure_ascii=False, indent=2)

    @staticmethod
    def deserialize(raw: str) -> EncryptedPayload:
        data = json.loads(raw)
        return EncryptedPayload.from_raw(data)
