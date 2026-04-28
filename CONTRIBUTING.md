# 贡献指南

感谢关注这个项目。当前项目以本地桌面工具为主，欢迎提交问题、改进建议和小范围修复。

## 本地开发

```bash
python3 -m pip install -r requirements.txt
python3 main.py
```

提交前请至少运行：

```bash
python3 -m compileall main.py app scripts
```

## 变更规范

- 保持功能变更聚焦，避免把格式化、重构和功能修复混在同一个提交里。
- 修改用户可见功能时，同步更新 `CHANGELOG.md`。
- 修改版本时，同步更新 `app/constants.py` 的 `APP_VERSION`。
- 不要提交本地票据、配置文件、API 密钥、调试日志或 `__pycache__`。

