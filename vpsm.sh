#!/usr/bin/env bash

set -Eeuo pipefail

APP_NAME="vps-dueguard"
LANG_CHOICE="zh"
SOURCE_DIR=""
INSTALL_DIR="/opt/vps-dueguard"
RUNTIME_DIR="/opt/vps-dueguard-runtime"
UV_DIR="$RUNTIME_DIR/uv"
UV_BIN="$UV_DIR/uv"
UV_CACHE_DIR="$RUNTIME_DIR/cache"
UV_CONFIG_HOME="$RUNTIME_DIR/config"
UV_PYTHON_INSTALL_DIR="$RUNTIME_DIR/python"
VENV_DIR="$INSTALL_DIR/.venv"
CONFIG_FILE="$INSTALL_DIR/config.yaml"
BIN_PATH="/usr/local/bin/vpsm"
BOT_SERVICE="/etc/systemd/system/vps-dueguard-bot.service"
DAILY_SERVICE="/etc/systemd/system/vps-dueguard-daily.service"
DAILY_TIMER="/etc/systemd/system/vps-dueguard-daily.timer"
RENEWALS_SERVICE="/etc/systemd/system/vps-dueguard-renewals.service"
RENEWALS_TIMER="/etc/systemd/system/vps-dueguard-renewals.timer"
TRAFFIC_SERVICE="/etc/systemd/system/vps-dueguard-traffic.service"
TRAFFIC_TIMER="/etc/systemd/system/vps-dueguard-traffic.timer"

MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10
UV_PYTHON_VERSION="3.11"
PREFERRED_PYTHON_SOURCE_VERSION="3.11.9"
PYTHON_BIN=""

on_error() {
    local line="$1"
    local command="$2"
    echo
    if [ "${LANG_CHOICE:-zh}" = "zh" ]; then
        echo "操作失败：第 ${line} 行，命令：${command}" >&2
        echo "请检查上方错误信息后重试。" >&2
    else
        echo "Operation failed at line ${line}: ${command}" >&2
        echo "Please check the error above and try again." >&2
    fi
}
trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

main() {
    require_root
    SOURCE_DIR="$(script_source_dir)"
    choose_language
    while true; do
        clear
        show_header
        show_main_menu
        printf "\n%s" "$(msg choose_option)"
        read_input "" choice
        case "$choice" in
            1) install_or_update ;;
            2) manage_providers ;;
            3) manage_telegram ;;
            4) manage_tests ;;
            5) manage_services ;;
            6) show_logs ;;
            7) uninstall_completely ;;
            8) exit 0 ;;
            *) pause "$(msg invalid_option)" ;;
        esac
    done
}

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "Please run with root privileges: sudo bash vpsm.sh"
        exit 1
    fi
}

script_source_dir() {
    local source_path
    source_path="${BASH_SOURCE[0]}"
    cd "$(dirname "$source_path")" && pwd
}

choose_language() {
    clear
    cat <<'EOF_LANG'
Select language / 选择语言

1. 中文
2. English
EOF_LANG
    printf "\n选择 / Choose [1]: "
    read_input "" choice
    case "$choice" in
        2) LANG_CHOICE="en" ;;
        *) LANG_CHOICE="zh" ;;
    esac
}

msg() {
    local key="$1"
    case "$LANG_CHOICE:$key" in
        zh:choose_option) printf "请选择: " ;;
        en:choose_option) printf "Choose an option: " ;;
        zh:invalid_option) printf "无效选项。" ;;
        en:invalid_option) printf "Invalid option." ;;
        zh:not_installed) printf "未安装" ;;
        en:not_installed) printf "not installed" ;;
        zh:installed) printf "已安装" ;;
        en:installed) printf "installed" ;;
        zh:active) printf "运行中" ;;
        en:active) printf "active" ;;
        zh:inactive) printf "未运行" ;;
        en:inactive) printf "inactive" ;;
        zh:unknown) printf "未知" ;;
        en:unknown) printf "unknown" ;;
        zh:configured) printf "已配置" ;;
        en:configured) printf "configured" ;;
        zh:not_configured) printf "未配置" ;;
        en:not_configured) printf "not configured" ;;
        zh:press_enter) printf "按回车继续。" ;;
        en:press_enter) printf "Press Enter to continue." ;;
        *) printf "%s" "$key" ;;
    esac
}

show_header() {
    local install_status bot_status daily_status renewals_status traffic_status python_status providers_status telegram_status
    if [ -d "$INSTALL_DIR" ]; then
        install_status="$(msg installed)"
    else
        install_status="$(msg not_installed)"
    fi
    bot_status="$(service_status vps-dueguard-bot.service)"
    daily_status="$(service_status vps-dueguard-daily.timer)"
    renewals_status="$(service_status vps-dueguard-renewals.timer)"
    traffic_status="$(service_status vps-dueguard-traffic.timer)"
    python_status="$(current_python_status)"
    providers_status="$(provider_count)"
    telegram_status="$(telegram_config_status)"
    if [ "$LANG_CHOICE" = "zh" ]; then
        cat <<EOF_HEADER
VPS DueGuard 设置

状态:
- 安装: $install_status
- Python: $python_status
- 服务商数量: $providers_status
- Telegram: $telegram_status
- Bot 服务: $bot_status
- 日报定时器: $daily_status
- 续费提醒定时器: $renewals_status
- 流量预警定时器: $traffic_status
EOF_HEADER
    else
        cat <<EOF_HEADER
VPS DueGuard Setup

Status:
- Install: $install_status
- Python: $python_status
- Providers: $providers_status
- Telegram: $telegram_status
- Bot service: $bot_status
- Daily timer: $daily_status
- Renewal timer: $renewals_status
- Traffic alert timer: $traffic_status
EOF_HEADER
    fi
}

current_python_status() {
    local saved_bin="$PYTHON_BIN"
    if select_python >/dev/null 2>&1; then
        "$PYTHON_BIN" -V 2>&1
    else
        printf "< %s.%s" "$MIN_PYTHON_MAJOR" "$MIN_PYTHON_MINOR"
    fi
    PYTHON_BIN="$saved_bin"
}

service_status() {
    local unit="$1"
    if ! command -v systemctl >/dev/null 2>&1; then
        msg unknown
        return
    fi
    if systemctl is-active --quiet "$unit" 2>/dev/null; then
        msg active
    else
        msg inactive
    fi
}

show_main_menu() {
    if [ "$LANG_CHOICE" = "zh" ]; then
        cat <<'EOF_MENU'

1. 安装 / 更新 VPS DueGuard
2. 服务商管理
3. Telegram 和提醒管理
4. 查询和测试
5. systemd 服务管理
6. 查看日志
7. 完整卸载
8. 退出
EOF_MENU
    else
        cat <<'EOF_MENU'

1. Install / Update VPS DueGuard
2. Provider management
3. Telegram and notification management
4. Query and tests
5. systemd service management
6. Show logs
7. Uninstall completely
8. Exit
EOF_MENU
    fi
}

install_or_update() {
    local was_installed bot_was_active
    if is_installed; then
        was_installed=1
    else
        was_installed=0
    fi
    if systemctl is-active --quiet vps-dueguard-bot.service 2>/dev/null; then
        bot_was_active=1
    else
        bot_was_active=0
    fi
    if ! install_core; then
        return
    fi
    repair_config || true
    if [ "$was_installed" -eq 0 ]; then
        first_run_wizard
    else
        if [ "$bot_was_active" -eq 1 ]; then
            systemctl restart vps-dueguard-bot.service || true
        fi
        if [ "$LANG_CHOICE" = "zh" ]; then
            pause "更新/修复完成。配置已保留。输入 vpsm 可随时回到管理界面。"
        else
            pause "Update / repair complete. Existing config was kept. Run vpsm to open the management menu."
        fi
    fi
}

is_installed() {
    [ -x "$BIN_PATH" ] && [ -d "$INSTALL_DIR" ]
}

install_core() {
    check_linux
    install_packages
    maybe_update_source_from_git || return 1
    ensure_python_ready
    cleanup_shell_startup_traces
    copy_project
    create_venv
    create_launcher
    create_systemd_units
    ensure_config_exists
    systemctl daemon-reload
}

first_run_wizard() {
    local answer
    echo
    echo "$(prompt install_complete_intro)"
    echo
    read_input "$(prompt wizard_configure_providers)" answer
    if ! is_no "$answer"; then
        rewrite_providers
    fi

    if [ "$(provider_count)" -gt 0 ]; then
        read_input "$(prompt wizard_test_query)" answer
        if ! is_no "$answer"; then
            run_vps_query_all
        fi
    fi

    read_input "$(prompt wizard_configure_telegram)" answer
    if ! is_no "$answer"; then
        edit_telegram_config
        if telegram_is_configured; then
            read_input "$(prompt wizard_test_telegram)" answer
            if ! is_no "$answer"; then
                run_telegram_test
            fi
        fi
    fi

    if telegram_is_configured; then
        read_input "$(prompt enable_timers)" answer
        if is_yes "$answer"; then
            ensure_traffic_timer
            systemctl enable --now vps-dueguard-daily.timer vps-dueguard-renewals.timer vps-dueguard-traffic.timer || true
        fi
        read_input "$(prompt enable_bot)" answer
        if is_yes "$answer"; then
            systemctl enable --now vps-dueguard-bot.service || true
        fi
    fi

    if [ "$LANG_CHOICE" = "zh" ]; then
        pause "安装/更新完成。以后输入 vpsm 即可进入管理界面。"
    else
        pause "Install / update complete. Run vpsm to open the management menu."
    fi
}

check_linux() {
    if [ ! -f /etc/os-release ]; then
        echo "$(prompt cannot_detect_linux)"
        exit 1
    fi
    # shellcheck disable=SC1091
    . /etc/os-release
    case "${ID:-}" in
        debian|ubuntu) ;;
        *)
            case "${ID_LIKE:-}" in
                *debian*) ;;
                *)
                    echo "$(prompt debian_only)"
                    exit 1
                    ;;
            esac
            ;;
    esac
    if ! command -v systemctl >/dev/null 2>&1; then
        echo "$(prompt systemd_required)"
        exit 1
    fi
}

install_packages() {
    echo "$(prompt installing_packages)"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y \
        ca-certificates \
        curl \
        wget \
        git \
        rsync \
        python3 \
        python3-venv \
        python3-pip
}

python_version_ok() {
    local bin="$1"
    "$bin" - <<PY_CHECK
import sys
raise SystemExit(0 if sys.version_info >= (${MIN_PYTHON_MAJOR}, ${MIN_PYTHON_MINOR}) else 1)
PY_CHECK
}

select_python() {
    local bin
    local candidates=(
        python3.12
        python3.11
        python3.10
        python3
        /usr/local/bin/python3.12
        /usr/local/bin/python3.11
        /usr/local/bin/python3.10
        /opt/python-${PREFERRED_PYTHON_SOURCE_VERSION}/bin/python3.11
    )
    local uv_python

    for bin in "${candidates[@]}"; do
        if command -v "$bin" >/dev/null 2>&1 && python_version_ok "$bin"; then
            PYTHON_BIN="$(command -v "$bin")"
            return 0
        fi
    done

    if [ -x "$UV_BIN" ]; then
        uv_python="$(uv_command python find "$UV_PYTHON_VERSION" 2>/dev/null || true)"
        if [ -n "$uv_python" ] && [ -x "$uv_python" ] && python_version_ok "$uv_python"; then
            PYTHON_BIN="$uv_python"
            return 0
        fi
    fi

    PYTHON_BIN=""
    return 1
}

ensure_python_ready() {
    if select_python; then
        echo "$(prompt python_selected) $($PYTHON_BIN -V 2>&1) ($PYTHON_BIN)"
        return 0
    fi

    show_python_requirement
    echo
    read_input "$(prompt confirm_python_upgrade)" answer
    if ! is_yes "$answer"; then
        echo "$(prompt python_upgrade_cancelled)"
        exit 1
    fi

    install_new_python

    if select_python; then
        echo "$(prompt python_selected) $($PYTHON_BIN -V 2>&1) ($PYTHON_BIN)"
        return 0
    fi

    echo "$(prompt python_install_failed)"
    exit 1
}

show_python_requirement() {
    local current_version=""
    if command -v python3 >/dev/null 2>&1; then
        current_version="$(python3 -V 2>&1)"
    else
        current_version="$(prompt python_not_found)"
    fi

    if [ "$LANG_CHOICE" = "zh" ]; then
        cat <<EOF_PY
检测到当前可用 Python 版本不满足要求。

当前 Python: $current_version
最低要求: Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+

VPS DueGuard 的依赖需要较新的 Python。脚本可以尝试安装一个新的 Python 运行时用于本项目。
优先使用系统软件源；Ubuntu 可选择添加 deadsnakes PPA；如果软件源没有合适版本，推荐使用 uv 下载独立 Python。

注意：脚本不会替换系统 /usr/bin/python3，避免破坏系统组件。
EOF_PY
    else
        cat <<EOF_PY
The available Python version does not meet the requirement.

Current Python: $current_version
Minimum required: Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+

VPS DueGuard dependencies require a newer Python runtime. This script can try to install a newer Python runtime for this project.
It tries the system repositories first; Ubuntu can optionally use the deadsnakes PPA; if no suitable package is available, uv can download a standalone Python runtime.

Note: this script will not replace /usr/bin/python3, so system components are not affected.
EOF_PY
    fi
}

install_new_python() {
    echo "$(prompt trying_install_python_from_apt)"
    if install_python_from_apt; then
        return 0
    fi

    if is_ubuntu; then
        echo
        read_input "$(prompt confirm_deadsnakes)" answer
        if is_yes "$answer"; then
            if install_python_from_deadsnakes; then
                return 0
            fi
        fi
    fi

    echo
    read_input "$(prompt confirm_uv_python)" answer
    if ! is_no "$answer"; then
        if install_python_from_uv; then
            return 0
        fi
    fi

    echo
    read_input "$(prompt confirm_source_python)" answer
    if is_yes "$answer"; then
        install_python_from_source
        return 0
    fi

    echo "$(prompt python_install_skipped)"
    exit 1
}

package_available() {
    local package="$1"
    apt-cache show "$package" >/dev/null 2>&1
}

install_python_from_apt() {
    local version package venv_package
    apt-get update
    for version in 3.12 3.11 3.10; do
        package="python${version}"
        venv_package="python${version}-venv"
        if package_available "$package" && package_available "$venv_package"; then
            echo "$(prompt installing_python_package) $package $venv_package"
            apt-get install -y "$package" "$venv_package"
            if command -v "python${version}" >/dev/null 2>&1 && python_version_ok "python${version}"; then
                PYTHON_BIN="$(command -v "python${version}")"
                return 0
            fi
        fi
    done
    return 1
}

is_ubuntu() {
    # shellcheck disable=SC1091
    . /etc/os-release
    [ "${ID:-}" = "ubuntu" ]
}

install_python_from_deadsnakes() {
    if ! is_ubuntu; then
        return 1
    fi

    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y software-properties-common ca-certificates curl
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update
    install_python_from_apt
}

install_python_from_uv() {
    local installer uv_python
    installer="/tmp/vps-dueguard-uv-install.sh"

    mkdir -p "$UV_DIR" "$UV_PYTHON_INSTALL_DIR" "$UV_CACHE_DIR" "$UV_CONFIG_HOME"
    echo "$(prompt installing_uv)"
    if command -v curl >/dev/null 2>&1; then
        curl -fLsS https://astral.sh/uv/install.sh -o "$installer" || return 1
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$installer" https://astral.sh/uv/install.sh || return 1
    else
        return 1
    fi

    UV_INSTALL_DIR="$UV_DIR" XDG_CONFIG_HOME="$UV_CONFIG_HOME" UV_CACHE_DIR="$UV_CACHE_DIR" sh "$installer" || return 1
    rm -f "$installer"

    echo "$(prompt installing_uv_python) Python $UV_PYTHON_VERSION"
    uv_command python install "$UV_PYTHON_VERSION" || return 1
    uv_python="$(uv_command python find "$UV_PYTHON_VERSION" 2>/dev/null || true)"
    if [ -n "$uv_python" ] && [ -x "$uv_python" ] && python_version_ok "$uv_python"; then
        PYTHON_BIN="$uv_python"
        return 0
    fi
    return 1
}

uv_command() {
    XDG_CONFIG_HOME="$UV_CONFIG_HOME" UV_CACHE_DIR="$UV_CACHE_DIR" UV_PYTHON_INSTALL_DIR="$UV_PYTHON_INSTALL_DIR" "$UV_BIN" "$@"
}

cleanup_shell_startup_traces() {
    local file backup_suffix
    backup_suffix="$(date +%Y%m%d%H%M%S)"

    for file in /root/.bashrc /root/.profile /root/.bash_profile /etc/profile /etc/bash.bashrc /etc/profile.d/*.sh; do
        [ -f "$file" ] || continue
        if grep -qE 'vps-dueguard-runtime/uv/env|bash_completions/python -m vps_dueguard\.sh|python -m vps_dueguard\.sh' "$file"; then
            cp "$file" "$file.bak.vps-dueguard.$backup_suffix" 2>/dev/null || true
            sed -i \
                -e '\#vps-dueguard-runtime/uv/env#d' \
                -e '\#bash_completions/python -m vps_dueguard\.sh#d' \
                -e '\#python -m vps_dueguard\.sh#d' \
                "$file"
        fi
    done

    rm -f "/root/.bash_completions/python -m vps_dueguard.sh"
}

install_python_from_source() {
    local build_root tarball source_dir prefix jobs
    build_root="/tmp/python-build-${PREFERRED_PYTHON_SOURCE_VERSION}"
    tarball="$build_root/Python-${PREFERRED_PYTHON_SOURCE_VERSION}.tgz"
    source_dir="$build_root/Python-${PREFERRED_PYTHON_SOURCE_VERSION}"
    prefix="/opt/python-${PREFERRED_PYTHON_SOURCE_VERSION}"
    jobs="$(nproc 2>/dev/null || echo 1)"
    if [ "$jobs" -gt 2 ]; then
        jobs=2
    fi

    echo "$(prompt installing_python_build_deps)"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y \
        build-essential \
        ca-certificates \
        curl \
        wget \
        libssl-dev \
        zlib1g-dev \
        libbz2-dev \
        libreadline-dev \
        libsqlite3-dev \
        libncursesw5-dev \
        xz-utils \
        tk-dev \
        libxml2-dev \
        libxmlsec1-dev \
        libffi-dev \
        liblzma-dev

    rm -rf "$build_root"
    mkdir -p "$build_root"

    echo "$(prompt downloading_python_source) Python-${PREFERRED_PYTHON_SOURCE_VERSION}"
    if command -v curl >/dev/null 2>&1; then
        curl -fL "https://www.python.org/ftp/python/${PREFERRED_PYTHON_SOURCE_VERSION}/Python-${PREFERRED_PYTHON_SOURCE_VERSION}.tgz" -o "$tarball"
    else
        wget -O "$tarball" "https://www.python.org/ftp/python/${PREFERRED_PYTHON_SOURCE_VERSION}/Python-${PREFERRED_PYTHON_SOURCE_VERSION}.tgz"
    fi

    tar -xzf "$tarball" -C "$build_root"

    echo "$(prompt compiling_python_source)"
    (
        cd "$source_dir"
        ./configure --prefix="$prefix" --with-ensurepip=install
        make -j "$jobs"
        make altinstall
    )

    ln -sf "$prefix/bin/python3.11" /usr/local/bin/python3.11
    "$prefix/bin/python3.11" -m pip install --upgrade pip setuptools wheel
}

copy_project() {
    local source_dir source_real install_real
    source_dir="$(install_source_dir)"
    source_real="$(readlink -f "$source_dir" 2>/dev/null || true)"
    install_real="$(readlink -f "$INSTALL_DIR" 2>/dev/null || true)"
    if [ -n "$source_real" ] && [ "$source_real" = "$install_real" ]; then
        return
    fi
    mkdir -p "$INSTALL_DIR"
    rsync -a --delete \
        --exclude ".venv" \
        --exclude ".pytest_cache" \
        --exclude "__pycache__" \
        --exclude ".vps_sessions" \
        --exclude ".vps_dueguard_state.json" \
        --exclude "config.yaml" \
        "$source_dir/" "$INSTALL_DIR/"
    printf "%s\n" "$source_dir" > "$INSTALL_DIR/.source_dir"
}

maybe_update_source_from_git() {
    local source_dir answer
    source_dir="$(install_source_dir)"
    if [ ! -d "$source_dir/.git" ]; then
        echo "$(prompt git_not_available_for_update)"
        return 0
    fi
    if ! command -v git >/dev/null 2>&1; then
        echo "$(prompt git_command_missing)"
        return 0
    fi
    echo "$(prompt git_update_source) $source_dir"
    read_input "$(prompt git_pull_question)" answer
    if is_no "$answer"; then
        echo "$(prompt git_pull_skipped)"
        return 0
    fi
    if git -C "$source_dir" pull --ff-only; then
        echo "$(prompt git_pull_done)"
    else
        echo "$(prompt git_pull_failed)"
        read_input "$(prompt continue_with_local_source)" answer
        if is_no "$answer" || [ -z "$answer" ]; then
            echo "$(prompt install_update_cancelled)"
            return 1
        fi
    fi
}

install_source_dir() {
    local source_real install_real original original_real
    source_real="$(readlink -f "$SOURCE_DIR" 2>/dev/null || true)"
    install_real="$(readlink -f "$INSTALL_DIR" 2>/dev/null || true)"
    if [ -n "$source_real" ] && [ "$source_real" = "$install_real" ]; then
        if [ -d "$SOURCE_DIR/.git" ]; then
            printf "%s" "$SOURCE_DIR"
            return
        fi
        original="$(original_source_dir)"
        original_real="$(readlink -f "$original" 2>/dev/null || true)"
        if [ -n "$original_real" ] && source_dir_has_project_markers "$original_real"; then
            printf "%s" "$original_real"
            return
        fi
    fi
    printf "%s" "$SOURCE_DIR"
}

create_venv() {
    echo "$(prompt creating_venv)"
    select_python
    echo "$(prompt python_selected) $($PYTHON_BIN -V 2>&1) ($PYTHON_BIN)"

    rm -rf "$VENV_DIR.tmp"
    "$PYTHON_BIN" -m venv "$VENV_DIR.tmp"
    "$VENV_DIR.tmp/bin/python" -m pip install --upgrade pip setuptools wheel
    "$VENV_DIR.tmp/bin/python" -m pip install -r "$INSTALL_DIR/requirements.txt"

    rm -rf "$VENV_DIR"
    mv "$VENV_DIR.tmp" "$VENV_DIR"
}

create_launcher() {
    cat > "$BIN_PATH" <<EOF_LAUNCHER
#!/usr/bin/env bash
cd "$INSTALL_DIR" || exit 1
if [ "\$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then
    exec sudo bash "$INSTALL_DIR/vpsm.sh"
  fi
  echo "Please run with root privileges: sudo vpsm"
  exit 1
fi
exec bash "$INSTALL_DIR/vpsm.sh"
EOF_LAUNCHER
    chmod +x "$BIN_PATH"
}

create_systemd_units() {
    cat > "$BOT_SERVICE" <<EOF_BOT
[Unit]
Description=VPS DueGuard Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV_DIR/bin/python -m vps_dueguard bot --config $CONFIG_FILE
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF_BOT

    cat > "$DAILY_SERVICE" <<EOF_DAILY_SERVICE
[Unit]
Description=VPS DueGuard Daily Report
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV_DIR/bin/python -m vps_dueguard notify daily --config $CONFIG_FILE
EOF_DAILY_SERVICE

    cat > "$DAILY_TIMER" <<'EOF_DAILY_TIMER'
[Unit]
Description=Run VPS DueGuard daily report

[Timer]
OnCalendar=*-*-* 08:05:00
Persistent=true

[Install]
WantedBy=timers.target
EOF_DAILY_TIMER

    cat > "$RENEWALS_SERVICE" <<EOF_RENEWALS_SERVICE
[Unit]
Description=VPS DueGuard Renewal Reminders
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV_DIR/bin/python -m vps_dueguard notify renewals --config $CONFIG_FILE
EOF_RENEWALS_SERVICE

    cat > "$RENEWALS_TIMER" <<'EOF_RENEWALS_TIMER'
[Unit]
Description=Run VPS DueGuard renewal reminders

[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF_RENEWALS_TIMER

    cat > "$TRAFFIC_SERVICE" <<EOF_TRAFFIC_SERVICE
[Unit]
Description=VPS DueGuard Traffic Alerts
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV_DIR/bin/python -m vps_dueguard notify traffic-alerts --config $CONFIG_FILE
EOF_TRAFFIC_SERVICE

    local traffic_interval
    traffic_interval="$(read_config_value notifications.traffic_alerts.check_interval_hours)"
    [ -z "$traffic_interval" ] && traffic_interval="6"

    cat > "$TRAFFIC_TIMER" <<EOF_TRAFFIC_TIMER
[Unit]
Description=Run VPS DueGuard traffic alerts

[Timer]
OnCalendar=*-*-* 00/${traffic_interval}:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF_TRAFFIC_TIMER
}

ensure_config_exists() {
    if [ ! -f "$CONFIG_FILE" ]; then
        write_config "" "" "" "21,14,7,3"
    fi
}

manage_providers() {
    ensure_installed || return
    while true; do
        clear
        show_provider_menu
        printf "\n%s" "$(msg choose_option)"
        read_input "" choice
        case "$choice" in
            1) list_providers; pause ;;
            2) add_provider ;;
            3) rewrite_providers ;;
            4) run_vps_query_all; pause "$(prompt query_finished)" ;;
            5) run_vps_query_provider; pause "$(prompt query_finished)" ;;
            6) return ;;
            *) pause "$(msg invalid_option)" ;;
        esac
    done
}

show_provider_menu() {
    if [ "$LANG_CHOICE" = "zh" ]; then
        cat <<'EOF_PROVIDER_MENU'
服务商管理

1. 查看当前服务商
2. 添加服务商
3. 重写全部服务商
4. 测试全部服务商
5. 测试指定服务商
6. 返回
EOF_PROVIDER_MENU
    else
        cat <<'EOF_PROVIDER_MENU'
Provider management

1. Show providers
2. Add provider
3. Rewrite all providers
4. Test all providers
5. Test one provider
6. Back
EOF_PROVIDER_MENU
    fi
}

list_providers() {
    if [ ! -f "$CONFIG_FILE" ] || [ "$(provider_count)" -eq 0 ]; then
        echo "$(prompt no_configured_providers)"
        return
    fi
    config_python providers-list
}

add_provider() {
    ensure_installed || return
    local name base_url username password
    read_input "$(prompt provider_name_required)" name
    if [ -z "$name" ]; then
        pause "$(prompt no_providers)"
        return
    fi
    read_input "$(prompt base_url)" base_url
    read_input "$(prompt username)" username
    read_input "$(prompt password)" password
    if ! add_provider_config "$name" "$base_url" "$username" "$password"; then
        pause "$(prompt config_save_failed)"
        return 0
    fi
    pause "$(prompt providers_saved)"
}

rewrite_providers() {
    ensure_installed || return
    local providers_yaml="" provider_entry
    echo "$(prompt configure_providers_intro)"
    while true; do
        echo
        provider_entry="$(collect_provider_entry)"
        [ -z "$provider_entry" ] && break
        providers_yaml="${providers_yaml}${provider_entry}"
        read_input "$(prompt add_another_provider)" again
        is_yes "$again" || break
    done
    if [ -z "$providers_yaml" ]; then
        pause "$(prompt no_providers)"
        return
    fi
    if ! save_config "$providers_yaml" "$(read_config_value telegram.bot_token)" "$(read_config_value telegram.chat_id)" "$(read_renewal_days)"; then
        return 0
    fi
    pause "$(prompt providers_saved)"
}

collect_provider_entry() {
    local name base_url username password
    read_input "$(prompt provider_name)" name
    [ -z "$name" ] && return
    read_input "$(prompt base_url)" base_url
    read_input "$(prompt username)" username
    read_input "$(prompt password)" password
    cat <<EOF_PROVIDER_ENTRY
  - name: $(yaml_escape "$name")
    base_url: $(yaml_escape "$base_url")
    username: $(yaml_escape "$username")
    password: $(yaml_escape "$password")
EOF_PROVIDER_ENTRY
}

manage_telegram() {
    ensure_installed || return
    while true; do
        clear
        show_telegram_menu
        printf "\n%s" "$(msg choose_option)"
        read_input "" choice
        case "$choice" in
            1) show_telegram_status; pause ;;
            2) edit_telegram_config ;;
            3) edit_renewal_days ;;
            4) edit_traffic_alert ;;
            5) run_telegram_test; pause "$(prompt telegram_test_finished)" ;;
            6) run_daily_report; pause ;;
            7) run_renewal_check; pause ;;
            8) run_traffic_check; pause ;;
            9) return ;;
            *) pause "$(msg invalid_option)" ;;
        esac
    done
}

show_telegram_menu() {
    if [ "$LANG_CHOICE" = "zh" ]; then
        cat <<'EOF_TELEGRAM_MENU'
Telegram 和提醒管理

1. 查看配置状态
2. 修改 Bot Token 和 Chat ID
3. 修改续费提醒天数
4. 修改流量预警设置
5. 测试 Telegram 消息
6. 发送一次日报
7. 执行一次续费提醒检查
8. 执行一次流量预警检查
9. 返回
EOF_TELEGRAM_MENU
    else
        cat <<'EOF_TELEGRAM_MENU'
Telegram and notification management

1. Show config status
2. Edit bot token and chat ID
3. Edit renewal reminder days
4. Edit traffic alert settings
5. Test Telegram message
6. Send one daily report
7. Run one renewal check
8. Run one traffic alert check
9. Back
EOF_TELEGRAM_MENU
    fi
}

show_telegram_status() {
    local token chat_id days traffic_enabled traffic_threshold traffic_interval
    token="$(read_config_value telegram.bot_token)"
    chat_id="$(read_config_value telegram.chat_id)"
    days="$(read_renewal_days)"
    traffic_enabled="$(read_config_value notifications.traffic_alerts.enabled)"
    traffic_threshold="$(read_config_value notifications.traffic_alerts.threshold)"
    traffic_interval="$(read_config_value notifications.traffic_alerts.check_interval_hours)"
    echo "Telegram: $(telegram_config_status)"
    if [ -n "$token" ]; then
        echo "Bot token: $token"
    fi
    if [ -n "$chat_id" ]; then
        echo "Chat ID: $chat_id"
    fi
    echo "Renewal days: $days"
    if [ "$traffic_enabled" = "false" ]; then
        echo "Traffic alerts: disabled"
    else
        echo "Traffic alerts: enabled (threshold: ${traffic_threshold:-80}%, interval: ${traffic_interval:-6}h)"
    fi
}

edit_telegram_config() {
    ensure_installed || return
    local bot_token chat_id days
    echo "$(prompt configure_telegram_intro)"
    read_input "$(prompt bot_token)" bot_token
    read_input "$(prompt chat_id)" chat_id
    read_renewal_days_prompt days
    [ -n "$days" ] || return 0
    if ! set_telegram_config "$bot_token" "$chat_id" "$days"; then
        pause "$(prompt config_save_failed)"
        return 0
    fi
    pause "$(prompt telegram_saved)"
}

edit_renewal_days() {
    ensure_installed || return
    local days
    read_renewal_days_prompt days
    [ -n "$days" ] || return 0
    if ! set_renewal_days_config "$days"; then
        pause "$(prompt config_save_failed)"
        return 0
    fi
    pause "$(prompt telegram_saved)"
}

edit_traffic_alert() {
    ensure_installed || return
    local current_enabled current_threshold current_interval answer threshold interval
    current_enabled="$(read_config_value notifications.traffic_alerts.enabled)"
    current_threshold="$(read_config_value notifications.traffic_alerts.threshold)"
    current_interval="$(read_config_value notifications.traffic_alerts.check_interval_hours)"
    [ -z "$current_enabled" ] && current_enabled="true"
    [ -z "$current_threshold" ] && current_threshold="80"
    [ -z "$current_interval" ] && current_interval="6"

    if [ "$LANG_CHOICE" = "zh" ]; then
        echo "当前流量预警: 已$([ "$current_enabled" = "false" ] && echo '禁用' || echo '启用'), 阈值: ${current_threshold}%, 检查间隔: ${current_interval}小时"
        read_input "是否启用流量预警？[Y/n]: " answer
        if [ "$answer" = "n" ] || [ "$answer" = "N" ]; then
            set_traffic_alert_config "false" "$current_threshold" "$current_interval"
            pause "$(prompt telegram_saved)"
            return 0
        fi
        read_input "流量预警阈值百分比 (1-100) [${current_threshold}]: " threshold
        [ -z "$threshold" ] && threshold="$current_threshold"
        read_input "检查间隔，小时 (1-168) [${current_interval}]: " interval
    else
        echo "Traffic alerts: $([ "$current_enabled" = "false" ] && echo 'disabled' || echo 'enabled'), threshold: ${current_threshold}%, interval: ${current_interval}h"
        read_input "Enable traffic alerts? [Y/n]: " answer
        if [ "$answer" = "n" ] || [ "$answer" = "N" ]; then
            set_traffic_alert_config "false" "$current_threshold" "$current_interval"
            pause "$(prompt telegram_saved)"
            return 0
        fi
        read_input "Traffic alert threshold percentage (1-100) [${current_threshold}]: " threshold
        [ -z "$threshold" ] && threshold="$current_threshold"
        read_input "Check interval in hours (1-168) [${current_interval}]: " interval
    fi

    [ -z "$interval" ] && interval="$current_interval"
    if ! [[ "$threshold" =~ ^[0-9]+$ ]] || [ "$threshold" -lt 1 ] || [ "$threshold" -gt 100 ]; then
        pause "$(prompt invalid_renewal_days)"
        return 0
    fi
    if ! [[ "$interval" =~ ^[0-9]+$ ]] || [ "$interval" -lt 1 ] || [ "$interval" -gt 168 ]; then
        pause "$(prompt invalid_renewal_days)"
        return 0
    fi
    if ! set_traffic_alert_config "true" "$threshold" "$interval"; then
        pause "$(prompt config_save_failed)"
        return 0
    fi
    pause "$(prompt telegram_saved)"
}

read_renewal_days_prompt() {
    local __var="$1"
    local raw_days normalized
    echo "$(prompt current_renewal_days) $(read_renewal_days)"
    read_input "$(prompt renewal_days)" raw_days
    normalized="$(normalize_renewal_days_input "$raw_days")"
    if [ -z "$normalized" ]; then
        pause "$(prompt invalid_renewal_days)"
        printf -v "$__var" '%s' ""
        return 0
    fi
    printf -v "$__var" '%s' "$normalized"
}

manage_tests() {
    ensure_installed || return
    while true; do
        clear
        show_tests_menu
        printf "\n%s" "$(msg choose_option)"
        read_input "" choice
        case "$choice" in
            1) run_vps_query_all; pause "$(prompt query_finished)" ;;
            2) run_vps_query_provider; pause "$(prompt query_finished)" ;;
            3) run_cost_summary; pause "$(prompt query_finished)" ;;
            4) run_telegram_test; pause "$(prompt telegram_test_finished)" ;;
            5) run_daily_report; pause ;;
            6) run_renewal_check; pause ;;
            7) run_traffic_check; pause ;;
            8) return ;;
            *) pause "$(msg invalid_option)" ;;
        esac
    done
}

show_tests_menu() {
    if [ "$LANG_CHOICE" = "zh" ]; then
        cat <<'EOF_TESTS_MENU'
查询和测试

1. 查询全部服务商
2. 查询指定服务商
3. 查询费用汇总
4. 测试 Telegram 消息
5. 发送一次日报
6. 执行一次续费提醒检查
7. 执行一次流量预警检查
8. 返回
EOF_TESTS_MENU
    else
        cat <<'EOF_TESTS_MENU'
Query and tests

1. Query all providers
2. Query one provider
3. Query cost summary
4. Test Telegram message
5. Send one daily report
6. Run one renewal check
7. Run one traffic alert check
8. Back
EOF_TESTS_MENU
    fi
}

run_vps_query_all() {
    run_python_cli list || true
}

run_cost_summary() {
    run_python_cli cost || true
}

run_vps_query_provider() {
    local provider
    read_input "$(prompt provider_name_short)" provider
    [ -z "$provider" ] && return
    run_python_cli list --provider "$provider" || true
}

run_telegram_test() {
    run_python_cli notify test || true
}

run_daily_report() {
    run_python_cli notify daily || true
}

run_renewal_check() {
    run_python_cli notify renewals || true
}

run_traffic_check() {
    run_python_cli notify traffic-alerts || true
}

run_python_cli() {
    local command_name="${1:-}"
    [ -n "$command_name" ] || return 1
    shift || true
    case "$command_name" in
        list|bot|cost)
            (cd "$INSTALL_DIR" && "$VENV_DIR/bin/python" -m vps_dueguard "$command_name" --config "$CONFIG_FILE" "$@")
            ;;
        notify)
            local subcommand="${1:-}"
            [ -n "$subcommand" ] || return 1
            shift || true
            (cd "$INSTALL_DIR" && "$VENV_DIR/bin/python" -m vps_dueguard notify "$subcommand" --config "$CONFIG_FILE" "$@")
            ;;
        *)
            return 1
            ;;
    esac
}

test_vps_query() {
    ensure_installed || return
    echo "$(prompt query_all)"
    echo "$(prompt query_one)"
    read_input "$(msg choose_option)" choice
    case "$choice" in
        2)
            run_vps_query_provider
            ;;
        *)
            run_vps_query_all
            ;;
    esac
    pause "$(prompt query_finished)"
}

test_telegram() {
    ensure_installed || return
    run_telegram_test
    pause "$(prompt telegram_test_finished)"
}

manage_services() {
    ensure_installed || return
    while true; do
        clear
        show_services_menu
        printf "\n%s" "$(msg choose_option)"
        read_input "" choice
        case "$choice" in
            1) systemctl enable --now vps-dueguard-bot.service || true; pause "$(prompt bot_started)" ;;
            2) systemctl stop vps-dueguard-bot.service || true; pause "$(prompt bot_stopped)" ;;
            3) systemctl restart vps-dueguard-bot.service || true; pause "$(prompt bot_restarted)" ;;
            4) systemctl status vps-dueguard-bot.service --no-pager || true; pause ;;
            5)
                ensure_traffic_timer
                systemctl enable --now vps-dueguard-daily.timer vps-dueguard-renewals.timer vps-dueguard-traffic.timer || true
                pause "$(prompt timers_enabled)"
                ;;
            6)
                systemctl disable --now vps-dueguard-daily.timer vps-dueguard-renewals.timer vps-dueguard-traffic.timer || true
                pause "$(prompt timers_disabled)"
                ;;
            7) systemctl list-timers --all | grep vps-dueguard || true; pause ;;
            8) return ;;
            *) pause "$(msg invalid_option)" ;;
        esac
    done
}

show_services_menu() {
    if [ "$LANG_CHOICE" = "zh" ]; then
        cat <<'EOF_SERVICES'
管理服务

1. 启动 Bot
2. 停止 Bot
3. 重启 Bot
4. 查看 Bot 状态
5. 启用定时器
6. 禁用定时器
7. 查看定时器
8. 返回
EOF_SERVICES
    else
        cat <<'EOF_SERVICES'
Manage services

1. Start bot
2. Stop bot
3. Restart bot
4. Bot status
5. Enable timers
6. Disable timers
7. Show timers
8. Back
EOF_SERVICES
    fi
}

show_logs() {
    ensure_installed || return
    echo "$(prompt bot_logs)"
    echo "$(prompt daily_logs)"
    echo "$(prompt renewal_logs)"
    if [ "$LANG_CHOICE" = "zh" ]; then
        echo "4. 流量预警日志"
    else
        echo "4. Traffic alert logs"
    fi
    read_input "$(msg choose_option)" choice
    case "$choice" in
        1) journalctl -u vps-dueguard-bot.service -n 80 --no-pager || true ;;
        2) journalctl -u vps-dueguard-daily.service -n 80 --no-pager || true ;;
        3) journalctl -u vps-dueguard-renewals.service -n 80 --no-pager || true ;;
        4) journalctl -u vps-dueguard-traffic.service -n 80 --no-pager || true ;;
        *) echo "$(msg invalid_option)" ;;
    esac
    pause
}

uninstall_completely() {
    local source_delete_dir first_confirm second_confirm
    source_delete_dir="$(safe_source_delete_dir || true)"
    if [ "$LANG_CHOICE" = "zh" ]; then
        cat <<EOF_UNINSTALL
这将删除:
- $INSTALL_DIR
- $RUNTIME_DIR
- $BIN_PATH
- 所有 vps-dueguard systemd units
- 原始源码目录: ${source_delete_dir:-不会删除，未通过安全检查}

直接按回车继续；输入任意内容取消。
EOF_UNINSTALL
    else
        cat <<EOF_UNINSTALL
This will delete:
- $INSTALL_DIR
- $RUNTIME_DIR
- $BIN_PATH
- all vps-dueguard systemd units
- source directory: ${source_delete_dir:-not removed; safety check failed}

Press Enter to continue; type anything to cancel.
EOF_UNINSTALL
    fi
    read_input "$(prompt uninstall_first_confirm)" first_confirm
    if [ -n "$first_confirm" ]; then
        pause "$(prompt uninstall_cancelled)"
        return
    fi
    read_input "$(prompt uninstall_second_confirm)" second_confirm
    if [ -n "$second_confirm" ]; then
        pause "$(prompt uninstall_cancelled)"
        return
    fi

    systemctl disable --now vps-dueguard-bot.service >/dev/null 2>&1 || true
    systemctl disable --now vps-dueguard-daily.timer >/dev/null 2>&1 || true
    systemctl disable --now vps-dueguard-renewals.timer >/dev/null 2>&1 || true
    cleanup_shell_startup_traces
    rm -f "$BOT_SERVICE" "$DAILY_SERVICE" "$DAILY_TIMER" "$RENEWALS_SERVICE" "$RENEWALS_TIMER" "$TRAFFIC_SERVICE" "$TRAFFIC_TIMER"
    rm -f "$BIN_PATH"
    rm -rf "$INSTALL_DIR"
    rm -rf "$RUNTIME_DIR"
    systemctl daemon-reload
    systemctl reset-failed >/dev/null 2>&1 || true
    if [ -n "$source_delete_dir" ]; then
        cd /
        rm -rf "$source_delete_dir"
    fi
    pause "$(prompt uninstall_done)"
}

safe_source_delete_dir() {
    local source_candidate source_real install_real
    source_candidate="$(original_source_dir)"
    source_real="$(readlink -f "$source_candidate" 2>/dev/null || true)"
    install_real="$(readlink -f "$INSTALL_DIR" 2>/dev/null || true)"
    [ -n "$source_real" ] || return 1
    [ "$source_real" != "$install_real" ] || return 1
    source_dir_has_project_markers "$source_real" || return 1
    source_dir_is_safe_to_delete "$source_real" || return 1
    printf "%s" "$source_real"
}

original_source_dir() {
    if [ -f "$INSTALL_DIR/.source_dir" ]; then
        sed -n '1p' "$INSTALL_DIR/.source_dir"
    else
        printf "%s" "$SOURCE_DIR"
    fi
}

source_dir_has_project_markers() {
    local dir="$1"
    [ -f "$dir/vpsm.sh" ] && [ -d "$dir/vps_dueguard" ] && [ -f "$dir/requirements.txt" ]
}

source_dir_is_safe_to_delete() {
    local dir="$1"
    case "$dir" in
        /|/root|/home|/opt|/usr|/tmp|/var|/etc|/bin|/sbin|/lib|/lib64|/boot|/dev|/proc|/run|/sys)
            return 1
            ;;
    esac
    case "$dir" in
        /root/*|/home/*|/tmp/*|/var/tmp/*|/opt/*)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

write_config() {
    local providers_yaml="$1"
    local bot_token="$2"
    local chat_id="$3"
    local renewal_days="$4"
    mkdir -p "$INSTALL_DIR"
    providers_yaml="$(clean_control_chars "$providers_yaml")"
    bot_token="$(clean_control_chars "$bot_token")"
    chat_id="$(clean_control_chars "$chat_id")"
    renewal_days="$(normalize_renewal_days_input "$renewal_days")"
    if [ -z "$renewal_days" ]; then
        echo "$(prompt invalid_renewal_days)"
        return 1
    fi
    config_python write "$providers_yaml" "$bot_token" "$chat_id" "$renewal_days"
    chmod 600 "$CONFIG_FILE"
}

save_config() {
    if write_config "$@"; then
        return 0
    fi
    pause "$(prompt config_save_failed)"
    return 1
}

add_provider_config() {
    local name="$1"
    local base_url="$2"
    local username="$3"
    local password="$4"
    name="$(clean_control_chars "$name")"
    base_url="$(clean_control_chars "$base_url")"
    username="$(clean_control_chars "$username")"
    password="$(clean_control_chars "$password")"
    config_python add-provider "$name" "$base_url" "$username" "$password"
    chmod 600 "$CONFIG_FILE"
}

set_telegram_config() {
    local bot_token="$1"
    local chat_id="$2"
    local renewal_days="$3"
    bot_token="$(clean_control_chars "$bot_token")"
    chat_id="$(clean_control_chars "$chat_id")"
    renewal_days="$(normalize_renewal_days_input "$renewal_days")"
    if [ -z "$renewal_days" ]; then
        echo "$(prompt invalid_renewal_days)"
        return 1
    fi
    config_python set-telegram "$bot_token" "$chat_id" "$renewal_days"
    chmod 600 "$CONFIG_FILE"
}

set_renewal_days_config() {
    local renewal_days="$1"
    renewal_days="$(normalize_renewal_days_input "$renewal_days")"
    if [ -z "$renewal_days" ]; then
        echo "$(prompt invalid_renewal_days)"
        return 1
    fi
    config_python set-renewal-days "$renewal_days"
    chmod 600 "$CONFIG_FILE"
}

set_traffic_alert_config() {
    local enabled="$1"
    local threshold="$2"
    local interval="${3:-6}"
    config_python set-traffic-alert "$enabled" "$threshold" "$interval"
    chmod 600 "$CONFIG_FILE"
    ensure_traffic_timer
    regenerate_traffic_timer
}

ensure_traffic_timer() {
    if [ -f "$TRAFFIC_TIMER" ]; then
        return 0
    fi
    create_systemd_units
    systemctl daemon-reload 2>/dev/null || true
}

regenerate_traffic_timer() {
    if [ ! -f "$TRAFFIC_TIMER" ]; then
        return 0
    fi
    local traffic_interval
    traffic_interval="$(read_config_value notifications.traffic_alerts.check_interval_hours)"
    [ -z "$traffic_interval" ] && traffic_interval="6"
    cat > "$TRAFFIC_TIMER" <<EOF_TRAFFIC_TIMER_REGEN
[Unit]
Description=Run VPS DueGuard traffic alerts

[Timer]
OnCalendar=*-*-* 00/${traffic_interval}:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF_TRAFFIC_TIMER_REGEN
    systemctl daemon-reload 2>/dev/null || true
}

repair_config() {
    if [ ! -f "$CONFIG_FILE" ]; then
        return 0
    fi
    config_python repair
    chmod 600 "$CONFIG_FILE"
}

provider_count() {
    if [ ! -f "$CONFIG_FILE" ]; then
        echo 0
        return
    fi
    config_python provider-count 2>/dev/null || echo 0
}

telegram_is_configured() {
    local token chat_id
    token="$(read_config_value telegram.bot_token)"
    chat_id="$(read_config_value telegram.chat_id)"
    [ -n "$token" ] && [ -n "$chat_id" ]
}

telegram_config_status() {
    if telegram_is_configured; then
        msg configured
    else
        msg not_configured
    fi
}

mask_secret() {
    local value="$1"
    local length
    length="${#value}"
    if [ "$length" -le 8 ]; then
        printf "********"
    else
        printf "%s****%s" "${value:0:4}" "${value: -4}"
    fi
}

read_providers_yaml() {
    if [ ! -f "$CONFIG_FILE" ]; then
        echo ""
        return
    fi
    config_python providers-yaml 2>/dev/null || true
}

read_config_value() {
    local key="$1"
    case "$key" in
        telegram.bot_token)
            config_python get bot_token 2>/dev/null || true
            ;;
        telegram.chat_id)
            config_python get chat_id 2>/dev/null || true
            ;;
        notifications.traffic_alerts.enabled)
            config_python get traffic_alerts_enabled 2>/dev/null || true
            ;;
        notifications.traffic_alerts.threshold)
            config_python get traffic_threshold 2>/dev/null || true
            ;;
        notifications.traffic_alerts.check_interval_hours)
            config_python get traffic_interval 2>/dev/null || true
            ;;
    esac
}

read_renewal_days() {
    config_python get renewal_days 2>/dev/null || echo "21,14,7,3"
}

config_python() {
    local action="$1"
    shift || true
    local python_bin="python3"
    if [ -x "$VENV_DIR/bin/python" ]; then
        python_bin="$VENV_DIR/bin/python"
    fi
    (cd "$INSTALL_DIR" 2>/dev/null || cd "$SOURCE_DIR") && "$python_bin" -m vps_dueguard.menu_config --config "$CONFIG_FILE" "$action" "$@"
}

normalize_renewal_days_input() {
    local value
    value="$(clean_control_chars "$1")"
    [ -z "$value" ] && value="21,14,7,3"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    if [[ ! "$value" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
        echo ""
        return
    fi
    echo "$value"
}

read_input() {
    local prompt_text="$1"
    local __var="$2"
    local value
    if [ -n "$prompt_text" ]; then
        read -e -r -p "$prompt_text" value
    else
        read -e -r value
    fi
    value="$(clean_control_chars "$value")"
    printf -v "$__var" '%s' "$value"
}

read_secret() {
    read_input "$1" "$2"
}

yaml_escape() {
    local value="$1"
    value="$(clean_control_chars "$value")"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '"%s"' "$value"
}

clean_control_chars() {
    local value="$1"
    local cleaned="" char
    local i
    for ((i = 0; i < ${#value}; i++)); do
        char="${value:i:1}"
        case "$char" in
            $'\b'|$'\177')
                cleaned="${cleaned%?}"
                ;;
            *)
                cleaned="${cleaned}${char}"
                ;;
        esac
    done
    printf "%s" "$cleaned" | tr -d '\000-\010\013\014\016-\037\177'
}

ensure_installed() {
    if [ ! -x "$BIN_PATH" ] || [ ! -d "$INSTALL_DIR" ]; then
        pause "$(prompt not_installed_hint)"
        return 1
    fi
    return 0
}

is_yes() {
    case "$1" in
        y|Y|yes|YES|Yes) return 0 ;;
        *) return 1 ;;
    esac
}

is_no() {
    case "$1" in
        n|N|no|NO|No) return 0 ;;
        *) return 1 ;;
    esac
}

pause() {
    local message="${1:-$(msg press_enter)}"
    echo
    read -r -p "$message" _
}

prompt() {
    local key="$1"
    case "$LANG_CHOICE:$key" in
        zh:enable_bot) printf "是否启用并启动 Telegram Bot 服务？[y/N]: " ;;
        en:enable_bot) printf "Enable and start Telegram bot service? [y/N]: " ;;
        zh:enable_timers) printf "是否启用日报、续费提醒和流量预警定时器？[y/N]: " ;;
        en:enable_timers) printf "Enable daily report, renewal, and traffic alert timers? [y/N]: " ;;
        zh:install_complete_intro) printf "核心环境已安装完成，下面进入首次配置向导。" ;;
        en:install_complete_intro) printf "Core environment is installed. Starting the first-run setup wizard." ;;
        zh:wizard_configure_providers) printf "现在配置服务商？推荐直接配置。[Y/n]: " ;;
        en:wizard_configure_providers) printf "Configure providers now? Recommended. [Y/n]: " ;;
        zh:wizard_test_query) printf "是否立即测试 VPS 查询？[Y/n]: " ;;
        en:wizard_test_query) printf "Test VPS query now? [Y/n]: " ;;
        zh:wizard_configure_telegram) printf "是否配置 Telegram 和提醒？可稍后在菜单中配置。[Y/n]: " ;;
        en:wizard_configure_telegram) printf "Configure Telegram and notifications? You can do this later from the menu. [Y/n]: " ;;
        zh:wizard_test_telegram) printf "是否发送 Telegram 测试消息？[Y/n]: " ;;
        en:wizard_test_telegram) printf "Send a Telegram test message? [Y/n]: " ;;
        zh:cannot_detect_linux) printf "无法检测 Linux 发行版。" ;;
        en:cannot_detect_linux) printf "Cannot detect Linux distribution." ;;
        zh:debian_only) printf "此脚本仅支持 Debian/Ubuntu。" ;;
        en:debian_only) printf "This script is intended for Debian/Ubuntu systems." ;;
        zh:systemd_required) printf "需要 systemd。" ;;
        en:systemd_required) printf "systemd is required." ;;
        zh:installing_packages) printf "正在安装系统依赖..." ;;
        en:installing_packages) printf "Installing system packages..." ;;
        zh:git_not_available_for_update) printf "当前安装来源不是 git 仓库，跳过在线拉取；将使用本地脚本文件安装/更新。" ;;
        en:git_not_available_for_update) printf "Install source is not a git repository. Skipping online pull and using local files." ;;
        zh:git_command_missing) printf "未找到 git，跳过在线拉取；将使用本地脚本文件安装/更新。" ;;
        en:git_command_missing) printf "git was not found. Skipping online pull and using local files." ;;
        zh:git_update_source) printf "检测到 git 源码目录:" ;;
        en:git_update_source) printf "Detected git source directory:" ;;
        zh:git_pull_question) printf "是否先从 GitHub 拉取最新代码？[Y/n]: " ;;
        en:git_pull_question) printf "Pull the latest code from GitHub first? [Y/n]: " ;;
        zh:git_pull_skipped) printf "已跳过 git pull，继续使用本地文件。" ;;
        en:git_pull_skipped) printf "Skipped git pull. Continuing with local files." ;;
        zh:git_pull_done) printf "GitHub 更新完成。" ;;
        en:git_pull_done) printf "GitHub update complete." ;;
        zh:git_pull_failed) printf "git pull 失败，可能是网络问题、本地有未提交修改，或远程历史无法快进。" ;;
        en:git_pull_failed) printf "git pull failed. This may be caused by network issues, local changes, or a non-fast-forward remote history." ;;
        zh:continue_with_local_source) printf "是否继续使用当前本地文件安装/更新？[y/N]: " ;;
        en:continue_with_local_source) printf "Continue installing/updating with current local files? [y/N]: " ;;
        zh:install_update_cancelled) printf "已取消本次安装/更新。" ;;
        en:install_update_cancelled) printf "Install/update cancelled." ;;
        zh:creating_venv) printf "正在创建 Python 虚拟环境..." ;;
        en:creating_venv) printf "Creating Python virtual environment..." ;;
        zh:python_selected) printf "使用 Python:" ;;
        en:python_selected) printf "Using Python:" ;;
        zh:python_not_found) printf "未找到 python3" ;;
        en:python_not_found) printf "python3 not found" ;;
        zh:confirm_python_upgrade) printf "是否现在安装/更新一个用于本项目的 Python 运行时？[y/N]: " ;;
        en:confirm_python_upgrade) printf "Install/upgrade a Python runtime for this project now? [y/N]: " ;;
        zh:python_upgrade_cancelled) printf "已取消。请先安装 Python 3.10+ 后再运行安装。" ;;
        en:python_upgrade_cancelled) printf "Cancelled. Please install Python 3.10+ and run the installer again." ;;
        zh:trying_install_python_from_apt) printf "正在尝试从系统软件源安装新版 Python..." ;;
        en:trying_install_python_from_apt) printf "Trying to install a newer Python from system repositories..." ;;
        zh:installing_python_package) printf "正在安装 Python 包:" ;;
        en:installing_python_package) printf "Installing Python packages:" ;;
        zh:confirm_deadsnakes) printf "系统软件源未找到合适版本。是否添加 Ubuntu deadsnakes PPA 并继续安装？[y/N]: " ;;
        en:confirm_deadsnakes) printf "No suitable version was found in current repositories. Add the Ubuntu deadsnakes PPA and continue? [y/N]: " ;;
        zh:confirm_uv_python) printf "仍未找到合适版本。是否使用 uv 下载独立 Python 3.11？推荐，通常不需要编译。[Y/n]: " ;;
        en:confirm_uv_python) printf "Still no suitable version found. Use uv to download standalone Python 3.11? Recommended, usually no compilation. [Y/n]: " ;;
        zh:confirm_source_python) printf "uv 安装失败或已跳过。是否最后尝试从源码安装 Python 3.11 到 /opt？这可能需要较长时间。[y/N]: " ;;
        en:confirm_source_python) printf "uv failed or was skipped. As a last resort, build Python 3.11 under /opt from source? This may take a long time. [y/N]: " ;;
        zh:python_install_skipped) printf "已跳过 Python 安装，无法继续安装 VPS DueGuard。" ;;
        en:python_install_skipped) printf "Python installation skipped. VPS DueGuard installation cannot continue." ;;
        zh:python_install_failed) printf "Python 安装失败，无法继续。" ;;
        en:python_install_failed) printf "Python installation failed. Cannot continue." ;;
        zh:installing_uv) printf "正在安装 uv 独立运行时管理器..." ;;
        en:installing_uv) printf "Installing uv standalone runtime manager..." ;;
        zh:installing_uv_python) printf "正在通过 uv 安装独立 Python:" ;;
        en:installing_uv_python) printf "Installing standalone Python via uv:" ;;
        zh:installing_python_build_deps) printf "正在安装 Python 源码编译依赖..." ;;
        en:installing_python_build_deps) printf "Installing Python build dependencies..." ;;
        zh:downloading_python_source) printf "正在下载 Python 源码:" ;;
        en:downloading_python_source) printf "Downloading Python source:" ;;
        zh:compiling_python_source) printf "正在编译并安装 Python，请耐心等待..." ;;
        en:compiling_python_source) printf "Compiling and installing Python. Please wait..." ;;
        zh:configure_providers_intro) printf "重写全部服务商。现有服务商配置会被替换。" ;;
        en:configure_providers_intro) printf "Rewrite all providers. Existing providers will be replaced." ;;
        zh:provider_name) printf "服务商名称，例如 provider-a（留空结束）: " ;;
        en:provider_name) printf "Provider name, e.g. provider-a (blank to finish): " ;;
        zh:provider_name_required) printf "服务商名称，例如 provider-a: " ;;
        en:provider_name_required) printf "Provider name, e.g. provider-a: " ;;
        zh:provider_name_short) printf "服务商名称: " ;;
        en:provider_name_short) printf "Provider name: " ;;
        zh:add_another_provider) printf "继续添加下一个服务商？[y/N]: " ;;
        en:add_another_provider) printf "Add another provider? [y/N]: " ;;
        zh:base_url) printf "Base URL，例如 https://example.com/: " ;;
        en:base_url) printf "Base URL, e.g. https://example.com/: " ;;
        zh:username) printf "用户名/邮箱: " ;;
        en:username) printf "Username/email: " ;;
        zh:password) printf "密码: " ;;
        en:password) printf "Password: " ;;
        zh:no_providers) printf "未输入服务商，保留现有配置。" ;;
        en:no_providers) printf "No providers entered. Keeping existing config." ;;
        zh:no_configured_providers) printf "还没有配置服务商。" ;;
        en:no_configured_providers) printf "No providers configured yet." ;;
        zh:providers_saved) printf "服务商配置已保存。" ;;
        en:providers_saved) printf "Providers saved." ;;
        zh:configure_telegram_intro) printf "配置 Telegram。" ;;
        en:configure_telegram_intro) printf "Configure Telegram." ;;
        zh:bot_token) printf "Bot token: " ;;
        en:bot_token) printf "Bot token: " ;;
        zh:chat_id) printf "Chat ID: " ;;
        en:chat_id) printf "Chat ID: " ;;
        zh:current_renewal_days) printf "当前续费提醒天数:" ;;
        en:current_renewal_days) printf "Current renewal reminder days:" ;;
        zh:renewal_days) printf "续费提醒天数，逗号分隔，例如 21,14,7,3；直接回车使用默认值: " ;;
        en:renewal_days) printf "Renewal reminder days, comma-separated, e.g. 21,14,7,3; press Enter for default: " ;;
        zh:invalid_renewal_days) printf "续费提醒天数格式无效，请使用逗号分隔数字，例如 21,14,7,3。" ;;
        en:invalid_renewal_days) printf "Invalid renewal reminder days. Use comma-separated numbers, e.g. 21,14,7,3." ;;
        zh:telegram_saved) printf "Telegram 配置已保存。" ;;
        en:telegram_saved) printf "Telegram config saved." ;;
        zh:config_save_failed) printf "配置保存失败，请检查输入格式后重试。" ;;
        en:config_save_failed) printf "Config save failed. Check the input format and try again." ;;
        zh:query_all) printf "1. 查询全部服务商" ;;
        en:query_all) printf "1. Query all providers" ;;
        zh:query_one) printf "2. 查询单个服务商" ;;
        en:query_one) printf "2. Query one provider" ;;
        zh:query_finished) printf "查询完成。" ;;
        en:query_finished) printf "Query finished." ;;
        zh:telegram_test_finished) printf "Telegram 测试完成。" ;;
        en:telegram_test_finished) printf "Telegram test finished." ;;
        zh:bot_started) printf "Bot 已启动。" ;;
        en:bot_started) printf "Bot started." ;;
        zh:bot_stopped) printf "Bot 已停止。" ;;
        en:bot_stopped) printf "Bot stopped." ;;
        zh:bot_restarted) printf "Bot 已重启。" ;;
        en:bot_restarted) printf "Bot restarted." ;;
        zh:timers_enabled) printf "定时器已启用。" ;;
        en:timers_enabled) printf "Timers enabled." ;;
        zh:timers_disabled) printf "定时器已禁用。" ;;
        en:timers_disabled) printf "Timers disabled." ;;
        zh:bot_logs) printf "1. Bot 日志" ;;
        en:bot_logs) printf "1. Bot logs" ;;
        zh:daily_logs) printf "2. 日报日志" ;;
        en:daily_logs) printf "2. Daily report logs" ;;
        zh:renewal_logs) printf "3. 续费提醒日志" ;;
        en:renewal_logs) printf "3. Renewal reminder logs" ;;
        zh:confirm) printf "确认: " ;;
        en:confirm) printf "Confirm: " ;;
        zh:uninstall_first_confirm) printf "第一次确认：直接按回车继续，输入任意内容取消: " ;;
        en:uninstall_first_confirm) printf "First confirmation: press Enter to continue, type anything to cancel: " ;;
        zh:uninstall_second_confirm) printf "最终确认：再次直接按回车立即卸载，输入任意内容取消: " ;;
        en:uninstall_second_confirm) printf "Final confirmation: press Enter again to uninstall now, type anything to cancel: " ;;
        zh:uninstall_cancelled) printf "已取消卸载。" ;;
        en:uninstall_cancelled) printf "Uninstall cancelled." ;;
        zh:uninstall_done) printf "VPS DueGuard 已完整删除。" ;;
        en:uninstall_done) printf "VPS DueGuard has been completely removed." ;;
        zh:not_installed_hint) printf "VPS DueGuard 尚未安装，请先运行选项 1。" ;;
        en:not_installed_hint) printf "VPS DueGuard is not installed. Run option 1 first." ;;
        *) printf "%s" "$key" ;;
    esac
}

main "$@"
