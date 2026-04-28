from __future__ import annotations

import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

try:
    from .app.config_manager import ConfigManager
    from .app.data_models import AppConfig
    from .app.encryption import EncryptionError
    from .app.gui.dialogs import ask_password
    from .app.gui.main_window import run_app
except ImportError:
    if __package__ in (None, ''):
        package_root = Path(__file__).resolve().parent
        sys.path.insert(0, str(package_root))
        from app.config_manager import ConfigManager  # type: ignore[import]
        from app.data_models import AppConfig  # type: ignore[import]
        from app.encryption import EncryptionError  # type: ignore[import]
        from app.gui.dialogs import ask_password  # type: ignore[import]
        from app.gui.main_window import run_app  # type: ignore[import]
    else:
        raise

def acquire_password(root: tk.Tk, config_manager: ConfigManager) -> tuple[str, AppConfig] | tuple[None, None]:
    if config_manager.config_path.exists():
        while True:
            password = ask_password(root, "输入密码", "请输入主密码:")
            if password is None:
                return None, None
            try:
                config = config_manager.load(password)
                return password, config
            except EncryptionError as exc:
                messagebox.showerror("错误", str(exc), parent=root)
    else:
        password = ask_password(root, "设置密码", "请设置主密码:", confirm=True)
        if not password:
            return None, None
        config = AppConfig()
        config_manager.save(password, config)
        return password, config


def main() -> None:
    config_manager = ConfigManager()
    root = tk.Tk()
    root.withdraw()
    password, config = acquire_password(root, config_manager)
    if not password or config is None:
        messagebox.showinfo("提示", "未输入密码，程序已退出", parent=root)
        root.destroy()
        sys.exit(0)
    root.destroy()
    run_app(config_manager, config, password)


if __name__ == "__main__":
    main()
