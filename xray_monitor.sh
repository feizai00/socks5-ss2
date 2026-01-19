#!/bin/bash
# 统一的Xray服务监控系统
# 合并了monitor.sh和service_monitor.sh的功能

set -euo pipefail

# 配置
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly CONFIG_DIR="$SCRIPT_DIR/data"
readonly SERVICE_DIR="$CONFIG_DIR/services"
readonly XRAY_BIN="$SCRIPT_DIR/xray"
readonly MONITOR_LOG="$CONFIG_DIR/monitor.log"
readonly MONITOR_PID="$CONFIG_DIR/monitor.pid"

# 颜色
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# 配置参数
MONITOR_INTERVAL=30
MAX_LOG_SIZE=10485760  # 10MB
ENABLE_EMAIL_ALERTS=false
ENABLE_WEBHOOK_ALERTS=false

# 日志函数
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $*"
    echo "[$timestamp] $*" >> "$MONITOR_LOG" 2>/dev/null || true
}

log_error() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "[$timestamp] ${RED}[ERROR]${NC} $*" >&2
    echo "[$timestamp] [ERROR] $*" >> "$MONITOR_LOG" 2>/dev/null || true
}

log_success() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "[$timestamp] ${GREEN}[SUCCESS]${NC} $*"
    echo "[$timestamp] [SUCCESS] $*" >> "$MONITOR_LOG" 2>/dev/null || true
}

log_warning() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "[$timestamp] ${YELLOW}[WARNING]${NC} $*"
    echo "[$timestamp] [WARNING] $*" >> "$MONITOR_LOG" 2>/dev/null || true
}

# 检查服务状态
check_service_status() {
    local port="$1"
    local service_path="$SERVICE_DIR/$port"
    local pid_file="$service_path/xray.pid"
    local config_file="$service_path/config.json"
    
    # 检查配置文件
    if [ ! -f "$config_file" ]; then
        echo "配置缺失"
        return 2
    fi
    
    # 检查是否过期
    local info_file="$service_path/info"
    if [ -f "$info_file" ]; then
        local expires_at=$(grep "EXPIRES_AT=" "$info_file" 2>/dev/null | cut -d'=' -f2 || echo "0")
        if [ -n "$expires_at" ] && [ "$expires_at" != "0" ]; then
            local current=$(date +%s)
            if [ "$current" -gt "$expires_at" ]; then
                echo "已过期"
                return 3
            fi
        fi
    fi
    
    # 检查进程状态
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            # 检查端口监听
            if command -v netstat >/dev/null 2>&1; then
                if netstat -tlnp 2>/dev/null | grep ":$port " >/dev/null; then
                    echo "运行中"
                    return 0
                else
                    echo "端口未监听"
                    return 1
                fi
            else
                echo "运行中"
                return 0
            fi
        else
            echo "进程停止"
            return 1
        fi
    else
        echo "未启动"
        return 1
    fi
}

# 启动服务
start_service() {
    local port="$1"
    local service_path="$SERVICE_DIR/$port"
    local config_file="$service_path/config.json"
    local log_file="$service_path/xray.log"
    local pid_file="$service_path/xray.pid"
    
    if [ ! -f "$config_file" ]; then
        log_error "端口 $port 配置文件不存在"
        return 1
    fi
    
    if [ ! -x "$XRAY_BIN" ]; then
        log_error "Xray二进制文件不可执行"
        return 1
    fi
    
    log "启动服务: 端口 $port"
    
    # 清理旧的PID文件
    rm -f "$pid_file"
    
    # 启动服务
    nohup "$XRAY_BIN" -config "$config_file" > "$log_file" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$pid_file"
    
    # 等待服务启动
    sleep 2
    
    if kill -0 "$new_pid" 2>/dev/null; then
        log_success "服务启动成功: 端口 $port (PID: $new_pid)"
        return 0
    else
        log_error "服务启动失败: 端口 $port"
        rm -f "$pid_file"
        return 1
    fi
}

# 停止服务
stop_service() {
    local port="$1"
    local pid_file="$SERVICE_DIR/$port/xray.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
            log "停止服务: 端口 $port (PID: $pid)"
            sleep 1
            
            # 强制杀死
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null || true
            fi
        fi
        rm -f "$pid_file"
    fi
}

# 重启服务
restart_service() {
    local port="$1"
    log "重启服务: 端口 $port"
    
    stop_service "$port"
    sleep 1
    start_service "$port"
}

# 发送警报
send_alert() {
    local message="$1"
    local severity="${2:-warning}"
    
    log_warning "警报: $message"
    
    # 这里可以添加邮件或webhook通知
    if [ "$ENABLE_EMAIL_ALERTS" = "true" ]; then
        # 发送邮件通知的代码
        :
    fi
    
    if [ "$ENABLE_WEBHOOK_ALERTS" = "true" ]; then
        # 发送webhook通知的代码
        :
    fi
}

# 清理日志
cleanup_logs() {
    # 清理监控日志
    if [ -f "$MONITOR_LOG" ]; then
        local size=$(stat -f%z "$MONITOR_LOG" 2>/dev/null || stat -c%s "$MONITOR_LOG" 2>/dev/null || echo 0)
        if [ "$size" -gt "$MAX_LOG_SIZE" ]; then
            tail -1000 "$MONITOR_LOG" > "$MONITOR_LOG.tmp"
            mv "$MONITOR_LOG.tmp" "$MONITOR_LOG"
            log "监控日志已轮转"
        fi
    fi
    
    # 清理服务日志
    for service_dir in "$SERVICE_DIR"/*; do
        if [ -d "$service_dir" ]; then
            local log_file="$service_dir/xray.log"
            if [ -f "$log_file" ]; then
                local size=$(stat -f%z "$log_file" 2>/dev/null || stat -c%s "$log_file" 2>/dev/null || echo 0)
                if [ "$size" -gt "$MAX_LOG_SIZE" ]; then
                    mv "$log_file" "$service_dir/xray.log.old"
                    touch "$log_file"
                    log "服务日志已轮转: $(basename "$service_dir")"
                fi
            fi
        fi
    done
}

# 主监控循环
monitor_loop() {
    log "服务监控启动 (PID: $$)"
    echo $$ > "$MONITOR_PID"
    
    local cycle_count=0
    
    while true; do
        cycle_count=$((cycle_count + 1))
        
        if [ ! -d "$SERVICE_DIR" ]; then
            sleep "$MONITOR_INTERVAL"
            continue
        fi
        
        local total=0
        local running=0
        local stopped=0
        local expired=0
        local restarted=0
        local failed=0
        
        for service_dir in "$SERVICE_DIR"/*; do
            if [ -d "$service_dir" ]; then
                local port=$(basename "$service_dir")
                total=$((total + 1))
                
                local status
                status=$(check_service_status "$port")
                local exit_code=$?
                
                case $exit_code in
                    0)  # 运行中
                        running=$((running + 1))
                        ;;
                    1)  # 停止，尝试重启
                        stopped=$((stopped + 1))
                        log_warning "服务停止: 端口 $port，尝试重启..."
                        
                        if start_service "$port"; then
                            restarted=$((restarted + 1))
                            send_alert "服务已重启: 端口 $port"
                        else
                            failed=$((failed + 1))
                            send_alert "服务重启失败: 端口 $port" "error"
                        fi
                        ;;
                    2)  # 配置缺失
                        log_error "服务配置缺失: 端口 $port"
                        failed=$((failed + 1))
                        ;;
                    3)  # 已过期
                        expired=$((expired + 1))
                        ;;
                esac
            fi
        done
        
        # 每10个周期显示一次统计信息
        if [ $((cycle_count % 10)) -eq 0 ]; then
            log "监控统计: 总数 $total, 运行 $running, 过期 $expired"
        fi
        
        # 如果有重启或失败的服务，记录详细信息
        if [ $restarted -gt 0 ] || [ $failed -gt 0 ]; then
            log "监控周期 $cycle_count: 重启 $restarted 个服务, 失败 $failed 个"
        fi
        
        # 每100个周期清理一次日志
        if [ $((cycle_count % 100)) -eq 0 ]; then
            cleanup_logs
        fi
        
        sleep "$MONITOR_INTERVAL"
    done
}

# 显示状态
show_status() {
    echo "========================================"
    echo "  Xray 服务监控状态"
    echo "========================================"
    echo ""
    
    if [ ! -d "$SERVICE_DIR" ]; then
        echo "❌ 服务目录不存在"
        return 1
    fi
    
    local total=0
    local running=0
    local stopped=0
    local expired=0
    local error=0
    
    printf "%-8s %-12s %-20s %-12s\n" "端口" "状态" "节点名称" "有效期"
    echo "--------------------------------------------------------"
    
    for service_dir in "$SERVICE_DIR"/*; do
        if [ -d "$service_dir" ]; then
            local port=$(basename "$service_dir")
            total=$((total + 1))
            
            local status
            status=$(check_service_status "$port")
            local exit_code=$?
            
            # 获取节点名称
            local node_name="未知"
            local info_file="$service_dir/info"
            if [ -f "$info_file" ]; then
                node_name=$(grep "NODE_NAME=" "$info_file" 2>/dev/null | cut -d'=' -f2- | head -c 15 || echo "未知")
            fi
            
            # 获取有效期
            local expire_info="永久"
            if [ -f "$info_file" ]; then
                local expires_at=$(grep "EXPIRES_AT=" "$info_file" 2>/dev/null | cut -d'=' -f2 || echo "0")
                if [ -n "$expires_at" ] && [ "$expires_at" != "0" ]; then
                    expire_info=$(date -d "@$expires_at" "+%m-%d %H:%M" 2>/dev/null || echo "无效")
                fi
            fi
            
            case $exit_code in
                0)
                    echo -e "$(printf "%-8s ${GREEN}%-12s${NC} %-20s %-12s" "$port" "$status" "$node_name" "$expire_info")"
                    running=$((running + 1))
                    ;;
                1)
                    echo -e "$(printf "%-8s ${RED}%-12s${NC} %-20s %-12s" "$port" "$status" "$node_name" "$expire_info")"
                    stopped=$((stopped + 1))
                    ;;
                2)
                    echo -e "$(printf "%-8s ${RED}%-12s${NC} %-20s %-12s" "$port" "$status" "$node_name" "$expire_info")"
                    error=$((error + 1))
                    ;;
                3)
                    echo -e "$(printf "%-8s ${YELLOW}%-12s${NC} %-20s %-12s" "$port" "$status" "$node_name" "$expire_info")"
                    expired=$((expired + 1))
                    ;;
            esac
        fi
    done
    
    echo ""
    echo "统计: 总数 $total | 运行 $running | 停止 $stopped | 过期 $expired | 错误 $error"
    echo ""
    
    # 检查监控进程状态
    if [ -f "$MONITOR_PID" ]; then
        local monitor_pid=$(cat "$MONITOR_PID")
        if kill -0 "$monitor_pid" 2>/dev/null; then
            echo -e "${GREEN}✅ 监控服务运行中${NC} (PID: $monitor_pid)"
        else
            echo -e "${RED}❌ 监控服务未运行${NC}"
            rm -f "$MONITOR_PID"
        fi
    else
        echo -e "${RED}❌ 监控服务未运行${NC}"
    fi
}

# 停止监控
stop_monitor() {
    if [ -f "$MONITOR_PID" ]; then
        local monitor_pid=$(cat "$MONITOR_PID")
        if kill -0 "$monitor_pid" 2>/dev/null; then
            kill "$monitor_pid"
            log "监控服务已停止"
        fi
        rm -f "$MONITOR_PID"
    else
        echo "监控服务未运行"
    fi
}

# 信号处理
cleanup() {
    log "监控服务停止"
    rm -f "$MONITOR_PID"
    exit 0
}

trap cleanup TERM INT

# 删除所有服务
delete_all_services() {
    echo "=== 删除所有服务 ==="
    echo ""
    
    # 检查是否有服务
    if [ ! -d "$SERVICE_DIR" ] || [ -z "$(ls -A "$SERVICE_DIR" 2>/dev/null)" ]; then
        echo "❌ 没有找到任何服务"
        return 0
    fi
    
    # 显示所有服务
    echo "即将删除以下服务："
    echo "================================"
    local count=0
    for service_dir in "$SERVICE_DIR"/*; do
        if [ -d "$service_dir" ]; then
            local port=$(basename "$service_dir")
            count=$((count + 1))
            
            local status
            status=$(check_service_status "$port")
            local node_name="未知"
            local info_file="$service_dir/info"
            if [ -f "$info_file" ]; then
                node_name=$(grep "NODE_NAME=" "$info_file" 2>/dev/null | cut -d'=' -f2- | head -c 15 || echo "未知")
            fi
            
            printf "%-8s %-12s %-20s\n" "$port" "$status" "$node_name"
        fi
    done
    echo "================================"
    echo -e "${RED}总计 $count 个服务将被删除${NC}"
    echo ""
    
    # 确认删除
    echo -e "${YELLOW}⚠️  警告：此操作将删除所有服务！${NC}"
    echo -n "请输入 'DELETE' 确认: "
    read confirm
    if [ "$confirm" != "DELETE" ]; then
        echo "❌ 操作已取消"
        return 0
    fi
    
    # 停止监控
    if [ -f "$MONITOR_PID" ]; then
        local monitor_pid=$(cat "$MONITOR_PID")
        if kill -0 "$monitor_pid" 2>/dev/null; then
            log "停止监控服务..."
            kill "$monitor_pid" 2>/dev/null || true
        fi
        rm -f "$MONITOR_PID"
    fi
    
    # 删除所有服务
    local deleted=0
    for service_dir in "$SERVICE_DIR"/*; do
        if [ -d "$service_dir" ]; then
            local port=$(basename "$service_dir")
            echo -n "删除端口 $port... "
            
            stop_service "$port"
            if rm -rf "$service_dir" 2>/dev/null; then
                echo -e "${GREEN}✅${NC}"
                deleted=$((deleted + 1))
            else
                echo -e "${RED}❌${NC}"
            fi
        fi
    done
    
    # 清理日志
    rm -f "$MONITOR_LOG"
    
    log_success "成功删除 $deleted 个服务"
    echo -e "${GREEN}🎉 所有服务已清理完毕！${NC}"
}

# 显示帮助
show_help() {
    echo "Xray服务监控工具"
    echo ""
    echo "用法: $0 [命令] [选项]"
    echo ""
    echo "命令:"
    echo "  start         - 启动监控服务（后台运行）"
    echo "  stop          - 停止监控服务"
    echo "  status        - 显示服务状态"
    echo "  restart PORT  - 重启指定端口服务"
    echo "  delete-all    - 删除所有服务"
    echo "  logs [PORT]   - 查看日志"
    echo "  cleanup       - 清理日志文件"
    echo "  help          - 显示帮助"
    echo ""
    echo "选项:"
    echo "  --interval N  - 设置监控间隔（秒，默认30）"
    echo "  --daemon      - 后台运行"
    echo ""
}

# 主函数
main() {
    # 确保目录存在
    mkdir -p "$CONFIG_DIR"
    
    case "${1:-help}" in
        "start")
            if [ -f "$MONITOR_PID" ]; then
                local monitor_pid=$(cat "$MONITOR_PID")
                if kill -0 "$monitor_pid" 2>/dev/null; then
                    echo "监控服务已在运行 (PID: $monitor_pid)"
                    exit 0
                fi
            fi
            
            # 检查是否后台运行
            if [ "${2:-}" = "--daemon" ] || [ "${2:-}" = "-d" ]; then
                nohup "$0" start-loop > /dev/null 2>&1 &
                echo "监控服务已启动（后台运行）"
            else
                monitor_loop
            fi
            ;;
        "start-loop")
            monitor_loop
            ;;
        "stop")
            stop_monitor
            ;;
        "status")
            show_status
            ;;
        "restart")
            if [ $# -lt 2 ]; then
                echo "请指定端口号"
                exit 1
            fi
            restart_service "$2"
            ;;
        "delete-all")
            delete_all_services
            ;;
        "logs")
            if [ $# -ge 2 ]; then
                local port="$2"
                local log_file="$SERVICE_DIR/$port/xray.log"
                if [ -f "$log_file" ]; then
                    tail -f "$log_file"
                else
                    echo "日志文件不存在: $log_file"
                fi
            else
                if [ -f "$MONITOR_LOG" ]; then
                    tail -f "$MONITOR_LOG"
                else
                    echo "监控日志不存在"
                fi
            fi
            ;;
        "cleanup")
            cleanup_logs
            ;;
        "help"|*)
            show_help
            ;;
    esac
}

main "$@"