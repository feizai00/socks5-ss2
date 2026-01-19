#!/bin/bash
# 统一的Xray诊断和修复工具
# 整合了之前多个诊断脚本的功能

set -euo pipefail

# 配置
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly CONFIG_DIR="$SCRIPT_DIR/data"
readonly SERVICE_DIR="$CONFIG_DIR/services"
readonly XRAY_BIN="$SCRIPT_DIR/xray"

# 颜色
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# 日志函数
log() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

# 系统诊断
diagnose_system() {
    log "开始系统诊断..."
    
    echo "系统信息:"
    echo "  OS: $(uname -s) $(uname -r)"
    echo "  架构: $(uname -m)"
    echo "  内存: $(free -h | grep Mem | awk '{print $3"/"$2}')"
    echo "  磁盘: $(df -h / | tail -1 | awk '{print $3"/"$2" ("$5" used)"}')"
    
    # 检查必要命令
    echo ""
    echo "依赖检查:"
    for cmd in curl wget unzip netstat; do
        if command -v "$cmd" >/dev/null 2>&1; then
            log_success "$cmd - 已安装"
        else
            log_warning "$cmd - 未安装"
        fi
    done
    
    # 检查端口使用情况
    echo ""
    echo "端口使用情况:"
    if command -v netstat >/dev/null 2>&1; then
        netstat -tlnp | grep LISTEN | head -10
    else
        log_warning "netstat未安装，无法检查端口"
    fi
}

# Xray诊断
diagnose_xray() {
    log "开始Xray诊断..."
    
    # 检查Xray二进制
    if [ -f "$XRAY_BIN" ]; then
        if [ -x "$XRAY_BIN" ]; then
            local version=$("$XRAY_BIN" version 2>/dev/null | head -1 || echo "无法获取版本")
            log_success "Xray二进制: $version"
        else
            log_error "Xray二进制不可执行"
        fi
    else
        log_error "Xray二进制不存在: $XRAY_BIN"
    fi
    
    # 检查服务目录
    if [ -d "$SERVICE_DIR" ]; then
        local service_count=$(find "$SERVICE_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)
        log "发现 $service_count 个服务配置"
        
        for service_dir in "$SERVICE_DIR"/*; do
            if [ -d "$service_dir" ]; then
                local port=$(basename "$service_dir")
                diagnose_service "$port"
            fi
        done
    else
        log_warning "服务目录不存在: $SERVICE_DIR"
    fi
}

# 单个服务诊断
diagnose_service() {
    local port="$1"
    local service_path="$SERVICE_DIR/$port"
    
    echo ""
    echo "服务诊断: 端口 $port"
    echo "=========================================="
    
    # 检查配置文件
    local config_file="$service_path/config.json"
    if [ -f "$config_file" ]; then
        log_success "配置文件存在"
        
        # 验证JSON格式
        if python3 -m json.tool "$config_file" >/dev/null 2>&1; then
            log_success "JSON格式正确"
        else
            log_error "JSON格式错误"
        fi
    else
        log_error "配置文件不存在: $config_file"
        return 1
    fi
    
    # 检查进程状态
    local pid_file="$service_path/xray.pid"
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            log_success "进程运行中 (PID: $pid)"
        else
            log_warning "PID文件存在但进程未运行 (PID: $pid)"
        fi
    else
        log_warning "PID文件不存在"
    fi
    
    # 检查端口监听
    if command -v netstat >/dev/null 2>&1; then
        if netstat -tlnp | grep ":$port " >/dev/null; then
            log_success "端口 $port 正在监听"
        else
            log_warning "端口 $port 未监听"
        fi
    fi
    
    # 检查日志文件
    local log_file="$service_path/xray.log"
    if [ -f "$log_file" ]; then
        local log_size=$(du -h "$log_file" | cut -f1)
        log "日志文件大小: $log_size"
        
        # 检查最近错误
        local errors=$(tail -50 "$log_file" | grep -i error | wc -l)
        if [ "$errors" -gt 0 ]; then
            log_warning "发现 $errors 个错误记录"
            echo "最近的错误:"
            tail -50 "$log_file" | grep -i error | tail -3
        else
            log_success "无错误记录"
        fi
    else
        log_warning "日志文件不存在"
    fi
    
    # 检查服务信息
    local info_file="$service_path/info"
    if [ -f "$info_file" ]; then
        echo "服务信息:"
        while IFS='=' read -r key value; do
            echo "  $key: $value"
        done < "$info_file"
    fi
}

# 快速修复
quick_fix() {
    log "开始快速修复..."
    
    # 修复权限
    if [ -f "$XRAY_BIN" ]; then
        chmod +x "$XRAY_BIN"
        log_success "修复Xray权限"
    fi
    
    # 修复目录权限
    if [ -d "$CONFIG_DIR" ]; then
        find "$CONFIG_DIR" -type d -exec chmod 755 {} \;
        find "$CONFIG_DIR" -type f -exec chmod 644 {} \;
        log_success "修复目录权限"
    fi
    
    # 清理僵尸PID文件
    local cleaned=0
    for service_dir in "$SERVICE_DIR"/*; do
        if [ -d "$service_dir" ]; then
            local pid_file="$service_dir/xray.pid"
            if [ -f "$pid_file" ]; then
                local pid=$(cat "$pid_file")
                if ! kill -0 "$pid" 2>/dev/null; then
                    rm -f "$pid_file"
                    log_success "清理无效PID文件: $(basename "$service_dir")"
                    cleaned=$((cleaned + 1))
                fi
            fi
        fi
    done
    
    if [ $cleaned -gt 0 ]; then
        log_success "清理了 $cleaned 个无效PID文件"
    fi
}

# 重启所有服务
restart_all_services() {
    log "重启所有服务..."
    
    # 停止所有服务
    for service_dir in "$SERVICE_DIR"/*; do
        if [ -d "$service_dir" ]; then
            local port=$(basename "$service_dir")
            local pid_file="$service_dir/xray.pid"
            
            if [ -f "$pid_file" ]; then
                local pid=$(cat "$pid_file")
                if kill -0 "$pid" 2>/dev/null; then
                    kill "$pid"
                    log "停止服务: 端口 $port"
                    sleep 1
                fi
                rm -f "$pid_file"
            fi
        fi
    done
    
    # 启动所有服务
    for service_dir in "$SERVICE_DIR"/*; do
        if [ -d "$service_dir" ]; then
            local port=$(basename "$service_dir")
            local config_file="$service_dir/config.json"
            local log_file="$service_dir/xray.log"
            local pid_file="$service_dir/xray.pid"
            
            if [ -f "$config_file" ]; then
                log "启动服务: 端口 $port"
                nohup "$XRAY_BIN" -config "$config_file" > "$log_file" 2>&1 &
                echo $! > "$pid_file"
                sleep 1
                
                if kill -0 $(cat "$pid_file") 2>/dev/null; then
                    log_success "服务启动成功: 端口 $port"
                else
                    log_error "服务启动失败: 端口 $port"
                fi
            fi
        fi
    done
}

# 清理系统
cleanup_system() {
    log "开始系统清理..."
    
    # 清理日志文件
    local cleaned_logs=0
    for service_dir in "$SERVICE_DIR"/*; do
        if [ -d "$service_dir" ]; then
            local log_file="$service_dir/xray.log"
            local old_log="$service_dir/xray.log.old"
            
            if [ -f "$log_file" ]; then
                local size=$(stat -f%z "$log_file" 2>/dev/null || stat -c%s "$log_file" 2>/dev/null || echo 0)
                if [ "$size" -gt 1048576 ]; then  # 1MB
                    mv "$log_file" "$old_log"
                    touch "$log_file"
                    log "轮转日志: $(basename "$service_dir")"
                    cleaned_logs=$((cleaned_logs + 1))
                fi
            fi
        fi
    done
    
    if [ $cleaned_logs -gt 0 ]; then
        log_success "轮转了 $cleaned_logs 个日志文件"
    fi
    
    # 清理临时文件
    find /tmp -name "xray*" -mtime +1 -delete 2>/dev/null || true
    log_success "清理临时文件"
}

# 显示使用帮助
show_help() {
    echo "Xray诊断和修复工具"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  system        - 系统诊断"
    echo "  xray          - Xray诊断"
    echo "  service PORT  - 单个服务诊断"
    echo "  fix           - 快速修复"
    echo "  restart       - 重启所有服务"
    echo "  cleanup       - 系统清理"
    echo "  all           - 完整诊断"
    echo "  help          - 显示帮助"
    echo ""
}

# 完整诊断
full_diagnosis() {
    echo "========================================"
    echo "  Xray 完整诊断报告"
    echo "========================================"
    echo ""
    
    diagnose_system
    echo ""
    diagnose_xray
    echo ""
    
    echo "========================================"
    echo "  诊断完成"
    echo "========================================"
}

# 主函数
main() {
    case "${1:-help}" in
        "system")
            diagnose_system
            ;;
        "xray")
            diagnose_xray
            ;;
        "service")
            if [ $# -lt 2 ]; then
                log_error "请提供端口号"
                exit 1
            fi
            diagnose_service "$2"
            ;;
        "fix")
            quick_fix
            ;;
        "restart")
            restart_all_services
            ;;
        "cleanup")
            cleanup_system
            ;;
        "all")
            full_diagnosis
            ;;
        "help"|*)
            show_help
            ;;
    esac
}

main "$@"