from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Optional


class PasswordDialog(simpledialog.Dialog):
    def __init__(self, parent: tk.Widget, title: str, prompt: str, confirm: bool = False):
        self.prompt = prompt
        self.require_confirm = confirm
        self._password_var = tk.StringVar()
        self._confirm_var = tk.StringVar()
        super().__init__(parent, title)

    def body(self, master: tk.Misc) -> tk.Entry:
        ttk.Label(master, text=self.prompt, wraplength=320, justify=tk.LEFT).grid(
            row=0, column=0, columnspan=2, pady=(4, 6), sticky="w"
        )
        ttk.Label(master, text="密码:").grid(row=1, column=0, sticky="e", padx=(0, 6))
        entry = ttk.Entry(master, textvariable=self._password_var, show="*")
        entry.grid(row=1, column=1, sticky="we")
        master.grid_columnconfigure(1, weight=1)
        if self.require_confirm:
            ttk.Label(master, text="确认密码:").grid(row=2, column=0, sticky="e", padx=(0, 6), pady=(6, 0))
            confirm_entry = ttk.Entry(master, textvariable=self._confirm_var, show="*")
            confirm_entry.grid(row=2, column=1, sticky="we", pady=(6, 0))
        return entry

    def validate(self) -> bool:
        password = self._password_var.get().strip()
        if not password:
            messagebox.showwarning("提示", "密码不能为空")
            return False
        if self.require_confirm:
            if password != self._confirm_var.get().strip():
                messagebox.showwarning("提示", "两次输入的密码不一致")
                return False
        return True

    def apply(self) -> None:
        self.result = self._password_var.get().strip()


def ask_password(parent: tk.Widget, title: str, prompt: str, confirm: bool = False) -> Optional[str]:
    dialog = PasswordDialog(parent, title=title, prompt=prompt, confirm=confirm)
    return dialog.result


def ask_text(parent: tk.Widget, title: str, prompt: str) -> Optional[str]:
    value = simpledialog.askstring(title=title, prompt=prompt, parent=parent)
    if value is None:
        return None
    value = value.strip()
    if not value:
        messagebox.showwarning("提示", "输入不能为空")
        return None
    return value
