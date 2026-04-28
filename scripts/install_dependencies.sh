#!/usr/bin/env bash
set -euo pipefail

TSINGHUA_PYPI_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
TSINGHUA_HOMEBREW_DOMAIN="https://mirrors.tuna.tsinghua.edu.cn"
TSINGHUA_HOMEBREW_API="${TSINGHUA_HOMEBREW_DOMAIN}/homebrew-bottles/api"
TSINGHUA_HOMEBREW_BOTTLE="${TSINGHUA_HOMEBREW_DOMAIN}/homebrew-bottles"
TSINGHUA_HOMEBREW_BREW_GIT="${TSINGHUA_HOMEBREW_DOMAIN}/git/homebrew/brew.git"
TSINGHUA_HOMEBREW_CORE_GIT="${TSINGHUA_HOMEBREW_DOMAIN}/git/homebrew/homebrew-core.git"
TSINGHUA_HOMEBREW_CASK_GIT="${TSINGHUA_HOMEBREW_DOMAIN}/git/homebrew/homebrew-cask.git"

PYTHON_BIN=${PYTHON_BIN:-python3}
LOG_PREFIX="[invoice-manager setup]"

info() {
    printf '%s %s\n' "${LOG_PREFIX}" "$1"
}

warn() {
    printf '%s WARNING: %s\n' "${LOG_PREFIX}" "$1" >&2
}

error_exit() {
    printf '%s ERROR: %s\n' "${LOG_PREFIX}" "$1" >&2
    exit 1
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

use_tsinghua_homebrew_mirror() {
    export HOMEBREW_BREW_GIT_REMOTE="${TSINGHUA_HOMEBREW_BREW_GIT}"
    export HOMEBREW_CORE_GIT_REMOTE="${TSINGHUA_HOMEBREW_CORE_GIT}"
    export HOMEBREW_CASK_GIT_REMOTE="${TSINGHUA_HOMEBREW_CASK_GIT}"
    export HOMEBREW_API_DOMAIN="${TSINGHUA_HOMEBREW_API}"
    export HOMEBREW_BOTTLE_DOMAIN="${TSINGHUA_HOMEBREW_BOTTLE}"
    info "已启用清华大学 Homebrew 镜像"
}

ensure_homebrew() {
    if command_exists brew; then
        info "检测到 Homebrew"
        return
    fi
    warn "未检测到 Homebrew，请先安装：https://mirrors.tuna.tsinghua.edu.cn/help/homebrew/"
    error_exit "安装 Homebrew 后再运行本脚本"
}

ensure_formula() {
    local formula="$1"
    if brew list --versions "${formula}" >/dev/null 2>&1; then
        info "依赖 ${formula} 已安装"
        return 0
    fi
    info "正在安装 ${formula}"
    brew install "${formula}"
}

refresh_python_bin() {
    if command_exists "${PYTHON_BIN}"; then
        return
    fi
    if command_exists python3; then
        PYTHON_BIN="python3"
        return
    fi
    for candidate in \
        "/opt/homebrew/opt/python@3.12/bin/python3" \
        "/opt/homebrew/opt/python@3.11/bin/python3" \
        "/usr/local/opt/python@3.12/bin/python3" \
        "/usr/local/opt/python@3.11/bin/python3"; do
        if [ -x "${candidate}" ]; then
            PYTHON_BIN="${candidate}"
            return
        fi
    done
    error_exit "未找到 python3 可执行文件"
}

ensure_python() {
    refresh_python_bin
    if "${PYTHON_BIN}" -c "import sys; assert sys.version_info >= (3, 10)" >/dev/null 2>&1; then
        info "当前 Python(${PYTHON_BIN}) 版本满足要求"
        return
    fi
    info "当前 Python 版本过低，尝试安装 python@3.12"
    ensure_formula python@3.12
    refresh_python_bin
}

ensure_pip() {
    if "${PYTHON_BIN}" -m pip --version >/dev/null 2>&1; then
        info "pip 已就绪"
        return
    fi
    info "未检测到 pip，正在运行 ensurepip"
    "${PYTHON_BIN}" -m ensurepip --upgrade
}

ensure_pip_mirror() {
    local current
    current=$("${PYTHON_BIN}" -m pip config get global.index-url 2>/dev/null || true)
    if [ "${current}" = "${TSINGHUA_PYPI_URL}" ]; then
        info "pip 已使用清华镜像"
        return
    fi
    info "配置 pip 使用清华镜像"
    "${PYTHON_BIN}" -m pip config set global.index-url "${TSINGHUA_PYPI_URL}" >/dev/null
}

upgrade_pip_tools() {
    info "升级 pip 与 setuptools (使用清华镜像)"
    "${PYTHON_BIN}" -m pip install --upgrade pip setuptools wheel --index-url "${TSINGHUA_PYPI_URL}"
}

ensure_tkinter() {
    if "${PYTHON_BIN}" - <<'PY' >/dev/null 2>&1
import tkinter
PY
    then
        info "检测到 tkinter"
        return
    fi
    warn "未检测到 tkinter，尝试通过 Homebrew 安装"
    local py_version
    py_version=$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    local formula_candidates=("python-tk@${py_version}" "python-tk" "tcl-tk")
    local installed=false
    for formula in "${formula_candidates[@]}"; do
        if brew info --formula "${formula}" >/dev/null 2>&1; then
            ensure_formula "${formula}"
            installed=true
            break
        fi
    done
    if [ "${installed}" != true ]; then
        warn "未找到匹配的 python-tk 公式，尝试安装 tcl-tk 并提示手动配置"
        ensure_formula tcl-tk
        warn "请参考 https://mirrors.tuna.tsinghua.edu.cn/help/homebrew/ 手动配置 python 与 tcl-tk"
    fi
    info "验证 tkinter 支持"
    if "${PYTHON_BIN}" - <<'PY'
import tkinter
root = tkinter.Tk()
root.withdraw()
root.destroy()
PY
    then
        info "tkinter 安装成功"
    else
        warn "自动检测 tkinter 仍失败，请手动检查 Python 与 tcl-tk 配置"
    fi
}

install_project_requirements() {
    local req_file
    if [ -f requirements.txt ]; then
        req_file="requirements.txt"
    elif [ -f invoice_manager_app/requirements.txt ]; then
        req_file="invoice_manager_app/requirements.txt"
    else
        info "未找到 requirements.txt，跳过 Python 包安装"
        return
    fi
    info "安装 ${req_file} 中列出的依赖"
    "${PYTHON_BIN}" -m pip install -r "${req_file}" --index-url "${TSINGHUA_PYPI_URL}"
}

ensure_tkinterdnd2() {
    if "${PYTHON_BIN}" -m pip show tkinterdnd2 >/dev/null 2>&1; then
        info "检测到 tkinterdnd2"
        return
    fi
    info "安装 tkinterdnd2 (用于拖拽文件识别)"
    "${PYTHON_BIN}" -m pip install tkinterdnd2 --index-url "${TSINGHUA_PYPI_URL}"
}

main() {
    info "开始检测并安装依赖"
    use_tsinghua_homebrew_mirror
    ensure_homebrew
    brew update
    ensure_python
    ensure_pip
    ensure_pip_mirror
    upgrade_pip_tools
    ensure_tkinter
    ensure_tkinterdnd2
    install_project_requirements
    info "依赖检测及安装完成"
    info "若使用虚拟环境，请确保运行脚本前已激活相应环境"
}

main "$@"
