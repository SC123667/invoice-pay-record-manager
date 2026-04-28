# 发票与支付记录管理工具

[![Python Check](https://github.com/SC123667/invoice-pay-record-manager/actions/workflows/python-check.yml/badge.svg)](https://github.com/SC123667/invoice-pay-record-manager/actions/workflows/python-check.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20desktop-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

一个面向个人报销、项目归档和财务凭证整理的本地桌面工具。它可以把发票和支付凭证按地区、类别、年月日归档，支持批量识别、金额汇总、拖拽识别和可配置的 OCR/视觉模型接口。

## 亮点

- 发票和支付凭证分流保存，自动按地区、一级类别、二级类别、日期目录归档。
- 支持单文件识别和批量识别，批量模式可自动分类并统计发票金额。
- 集成硅基流动视觉语言模型和 SimpleTex 风格签名接口，适合识别发票日期、支付日期、类别与金额。
- 默认发票来源目录指向微信文件目录，方便直接从微信接收文件中选取发票。
- 配置文件本地加密保存，API Token、接口密钥和常用目录不会明文落盘。
- 支持拖拽文件识别，常用类别、日期和公务卡标记可记忆上次选择。

## 适用场景

- 报销前把微信、邮箱、下载目录里的发票集中整理。
- 按工程项目、地区或月份沉淀发票和支付记录。
- 快速区分加油、住宿、过路费、五金等常见费用类别。
- 批量识别票据金额，提前核对一批报销材料的总额。

## 项目结构

```text
.
├── app/
│   ├── api_client.py       # OCR/视觉模型接口与识别结果解析
│   ├── config_manager.py   # 加密配置读写
│   ├── constants.py        # 应用常量与版本号
│   ├── data_models.py      # 配置数据模型
│   └── gui/                # Tkinter 桌面界面
├── scripts/
│   ├── install_dependencies.sh
│   └── pdf_to_images.py
├── main.py
└── CHANGELOG.md
```

## 安装

推荐 Python 3.10 或更高版本。macOS 可直接运行依赖安装脚本：

```bash
chmod +x scripts/install_dependencies.sh
./scripts/install_dependencies.sh
```

也可以手动安装 Python 依赖：

```bash
python3 -m pip install -r requirements.txt
```

如果本机 Python 没有 `tkinter`，请先安装支持 Tk 的 Python 版本。macOS Homebrew 用户通常可以安装 `python-tk` 或使用脚本自动检查。

## 运行

```bash
python3 main.py
```

首次启动会要求设置主密码。之后配置会保存到用户目录下的加密配置文件中。

## 默认目录

发票上传来源、支付凭证来源和识别文件默认位置会使用同一个默认目录。应用启动时会优先读取环境变量：

```bash
export INVOICE_MANAGER_DEFAULT_SOURCE_DIR="/path/to/your/invoice/files"
```

如果未设置环境变量，应用会在本机微信文件目录下自动探测可用的 `msg/file` 文件夹。仓库不会保存个人用户名、微信账号目录或本机绝对路径。

你可以在应用的“设置”窗口里分别改成任意常用文件夹。

## 识别接口

应用支持两类识别方式：

- 硅基流动视觉语言模型：适合直接识别图片或由 PDF 转换得到的图片。
- SimpleTex 风格接口：适合已有 App ID、App Secret 和签名接口的场景。

默认提示词会要求模型返回 JSON，并优先识别：

- `invoice_date`
- `payment_date`
- `category`
- `amount`

类别默认覆盖加油、住宿、过路费、五金和其他。

## 开发检查

```bash
python3 -m compileall main.py app scripts
```

## 版本记录

当前版本见 [CHANGELOG.md](CHANGELOG.md)。每次功能更新或重要修复都应同步更新 `app/constants.py` 中的 `APP_VERSION` 和更新记录。

## 许可证

本项目使用 MIT License，详见 [LICENSE](LICENSE)。
