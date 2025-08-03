#!/bin/bash
# Xray服务监控脚本 - 自动检测和重启停止的服务

set -euo pipefail

# 配置
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly CONFIG_DIR="$SCRIPT_DIR/data"
readonly SERVICE_DIR="$CONFIG_DIR/services"
readonly XRAY_BIN="$SCRIPT_DIR/xray"
readonly MONITOR_LOG="$CONFIG_DIR/monitor.log"

# 颜色
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly NC='\033[0m'

# 日志函数
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $*" | tee -a "$MONITOR_LOG"
}

log_error() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "[$timestamp] ${RED}[错误]${NC} $*" | tee -a "$MONITOR_LOG"
}

log_success() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "[$timestamp] ${GREEN}[成功]${NC} $*" | tee -a "$MONITOR_LOG"
}

log_warning() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "[$timestamp] ${YELLOW}[警告]${NC} $*" | tee -a "$MONITOR_LOG"
}

# 检查服务状态
check_status() {
    local port="$1"
    local pid_file="$SERVICE_DIR/$port/xray.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo "运行中"
        else
            echo "已停止"
            rm -f "$pid_file"
        fi
    else
        echo "已停止"
    fi
}

# 启动服务
start_service() {
    local port="$1"
    local config_file="$SERVICE_DIR/$port/config.json"
    local pid_file="$SERVICE_DIR/$port/xray.pid"
    local log_file="$SERVICE_DIR/$port/xray.log"
    
    # 检查是否已运行
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        rm -f "$pid_file"
    fi
    
    # 启动
    nohup "$XRAY_BIN" run -config "$config_file" > "$log_file" 2>&1 &
    local pid=$!
    echo "$pid" > "$pid_file"
    
    sleep 2
    if kill -0 "$pid" 2>/dev/null; then
        log_success "端口 $port 启动成功 (PID: $pid)"
        return 0
    else
        log_error "端口 $port 启动失败"
        rm -f "$pid_file"
        return 1
    fi
}

# 监控所有服务
monitor_services() {
    if [ ! -d "$SERVICE_DIR" ] || [ -z "$(ls -A "$SERVICE_DIR" 2>/dev/null)" ]; then
        log "没有找到任何服务配置"
        return
    fi
    
    local checked=0
    local restarted=0
    local failed=0
    
    for port_dir in "$SERVICE_DIR"/*; do
        if [ -d "$port_dir" ]; then
            local port=$(basename "$port_dir")
            local status=$(check_status "$port")
            checked=$((checked + 1))
            
            if [ "$status" = "已停止" ]; then
                log_warning "发现停止的服务: 端口 $port"
                if start_service "$port"; then
                    restarted=$((restarted + 1))
                else
                    failed=$((failed + 1))
                fi
            fi
        fi
    done
    
    if [ $restarted -gt 0 ] || [ $failed -gt 0 ]; then
        log "监控完成: 检查了 $checked 个服务, 重启了 $restarted 个, 失败 $failed 个"
    fi
}

# 显示帮助
show_help() {
    echo "Xray服务监控脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -m, --monitor     执行一次监控检查"
    echo "  -d, --daemon      以守护进程模式运行 (每5分钟检查一次)"
    echo "  -s, --status      显示所有服务状态"
    echo "  -l, --log         显示监控日志"
    echo "  -h, --help        显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 -m             # 执行一次监控"
    echo "  $0 -d             # 启动守护进程"
    echo "  $0 -s             # 显示服务状态"
}

# 显示服务状态
show_status() {
    if [ ! -d "$SERVICE_DIR" ] || [ -z "$(ls -A "$SERVICE_DIR" 2>/dev/null)" ]; then
        echo "没有找到任何服务配置"
        return
    fi
    
    echo "=== 服务状态 ==="
    printf "%-8s %-10s %-15s\n" "端口" "状态" "PID"
    echo "--------------------------------"
    
    for port_dir in "$SERVICE_DIR"/*; do
        if [ -d "$port_dir" ]; then
            local port=$(basename "$port_dir")
            local status=$(check_status "$port")
            local pid="N/A"
            
            if [ "$status" = "运行中" ]; then
                local pid_file="$port_dir/xray.pid"
                if [ -f "$pid_file" ]; then
                    pid=$(cat "$pid_file")
                fi
            fi
            
            printf "%-8s %-10s %-15s\n" "$port" "$status" "$pid"
        fi
    done
}

# 守护进程模式
daemon_mode() {
    log "启动守护进程模式，每5分钟检查一次服务状态"
    
    # 创建PID文件
    local daemon_pid_file="$CONFIG_DIR/monitor.pid"
    echo $$ > "$daemon_pid_file"
    
    # 清理函数
    cleanup() {
        log "停止监控守护进程"
        rm -f "$daemon_pid_file"
        exit 0
    }
    
    # 设置信号处理
    trap cleanup SIGTERM SIGINT
    
    while true; do
        monitor_services
        sleep 300  # 5分钟
    done
}

# 显示日志
show_log() {
    if [ -f "$MONITOR_LOG" ]; then
        echo "=== 监控日志 (最后50行) ==="
        tail -50 "$MONITOR_LOG"
    else
        echo "监控日志文件不存在"
    fi
}

# 主程序
main() {
    # 创建必要的目录
    mkdir -p "$CONFIG_DIR"
    
    # 检查Xray二进制文件
    if [ ! -f "$XRAY_BIN" ]; then
        log_error "Xray二进制文件不存在: $XRAY_BIN"
        echo "请先运行主脚本下载Xray"
        exit 1
    fi
    
    # 处理命令行参数
    case "${1:-}" in
        -m|--monitor)
            log "开始监控检查..."
            monitor_services
            ;;
        -d|--daemon)
            daemon_mode
            ;;
        -s|--status)
            show_status
            ;;
        -l|--log)
            show_log
            ;;
        -h|--help|"")
            show_help
            ;;
        *)
            echo "未知选项: $1"
            echo "使用 -h 或 --help 查看帮助"
            exit 1
            ;;
    esac
}

# 启动
main "$@"
