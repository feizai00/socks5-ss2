#!/bin/bash

# 获取脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/data"
SERVICE_DIR="$CONFIG_DIR/services"
MONITOR_LOG="$CONFIG_DIR/monitor.log"
MAIN_SCRIPT="$SCRIPT_DIR/xray_converter_simple.sh"

# 日志函数
log_monitor() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$MONITOR_LOG"
}

# 检查服务状态
check_service_status() {
    local port="$1"
    local pid_file="$SERVICE_DIR/$port/xray.pid"

    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            return 0  # 运行中
        else
            return 1  # 已停止
        fi
    else
        return 1  # 已停止
    fi
}

# 重启服务
restart_service() {
    local port="$1"
    log_monitor "检测到端口 $port 服务停止，正在重启..."

    # 调用主脚本的启动函数
    if bash "$MAIN_SCRIPT" start_single_service "$port" >> "$MONITOR_LOG" 2>&1; then
        log_monitor "端口 $port 服务重启成功"
        return 0
    else
        log_monitor "端口 $port 服务重启失败"
        return 1
    fi
}

# 主监控循环
main_monitor() {
    log_monitor "服务监控启动"

    while true; do
        if [ ! -d "$SERVICE_DIR" ]; then
            sleep 30
            continue
        fi

        local checked=0
        local restarted=0
        local failed=0

        for port_dir in "$SERVICE_DIR"/*; do
            if [ -d "$port_dir" ]; then
                local port=$(basename "$port_dir")
                checked=$((checked + 1))

                # 检查是否过期
                local info_file="$port_dir/info"
                if [ -f "$info_file" ]; then
                    local expires_at=$(grep "EXPIRES_AT=" "$info_file" 2>/dev/null | cut -d'=' -f2)
                    if [ -n "$expires_at" ] && [ "$expires_at" != "0" ]; then
                        local current=$(date +%s)
                        if [ "$current" -gt "$expires_at" ]; then
                            # 服务已过期，跳过监控
                            continue
                        fi
                    fi
                fi

                if ! check_service_status "$port"; then
                    if restart_service "$port"; then
                        restarted=$((restarted + 1))
                    else
                        failed=$((failed + 1))
                    fi
                fi
            fi
        done

        if [ $restarted -gt 0 ] || [ $failed -gt 0 ]; then
            log_monitor "监控周期完成: 检查 $checked 个服务, 重启 $restarted 个, 失败 $failed 个"
        fi

        sleep 30
    done
}

# 信号处理
cleanup() {
    log_monitor "服务监控停止"
    exit 0
}

trap cleanup TERM INT

# 启动监控
main_monitor
