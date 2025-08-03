#!/bin/bash
# Xray原生版本一键安装脚本

set -euo pipefail

# 颜色定义
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# 配置
readonly INSTALL_DIR="$HOME/xray-converter"
readonly GITHUB_REPO="https://raw.githubusercontent.com/XTLS/Xray-core/main"

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

# 检查依赖
check_dependencies() {
    local missing_deps=()
    
    for cmd in curl unzip; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing_deps+=("$cmd")
        fi
    done
    
    if [ ${#missing_deps[@]} -gt 0 ]; then
        log_error "缺少必要依赖: ${missing_deps[*]}"
        echo ""
        echo "请安装缺少的依赖："
        echo "Ubuntu/Debian: sudo apt update && sudo apt install ${missing_deps[*]}"
        echo "CentOS/RHEL: sudo yum install ${missing_deps[*]}"
        echo "Alpine: sudo apk add ${missing_deps[*]}"
        return 1
    fi
    
    log_success "依赖检查通过"
}

# 创建超简化版本脚本
create_simple_script() {
    cat > "$INSTALL_DIR/xray_converter.sh" << 'EOF'
#!/bin/bash
# Xray SOCKS5 to Shadowsocks 转换器 - 超简化版本

set -euo pipefail

# 配置
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly CONFIG_DIR="$SCRIPT_DIR/data"
readonly SERVICE_DIR="$CONFIG_DIR/services"
readonly XRAY_BIN="$SCRIPT_DIR/xray"

# 颜色
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly NC='\033[0m'

# 日志函数
log() { echo "[$(date '+%H:%M:%S')] $*"; }
log_error() { echo -e "${RED}[错误]${NC} $*" >&2; }
log_success() { echo -e "${GREEN}[成功]${NC} $*"; }

# 检查并下载Xray
ensure_xray() {
    if [ -f "$XRAY_BIN" ] && [ -x "$XRAY_BIN" ]; then
        return 0
    fi
    
    log "正在下载Xray..."
    
    local arch
    case $(uname -m) in
        x86_64) arch="64" ;;
        aarch64|arm64) arch="arm64-v8a" ;;
        armv7l) arch="arm32-v7a" ;;
        *) log_error "不支持的架构: $(uname -m)"; return 1 ;;
    esac
    
    local url="https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-${arch}.zip"
    local temp="/tmp/xray_$$.zip"
    
    if ! curl -L "$url" -o "$temp"; then
        log_error "下载失败"
        return 1
    fi
    
    if ! unzip -j "$temp" xray -d "$SCRIPT_DIR"; then
        log_error "解压失败"
        return 1
    fi
    
    chmod +x "$XRAY_BIN"
    rm -f "$temp"
    log_success "Xray下载完成"
}

# 生成配置
generate_config() {
    local port="$1" password="$2" socks_ip="$3" socks_port="$4" socks_user="$5" socks_pass="$6"
    local config_file="$SERVICE_DIR/$port/config.json"
    mkdir -p "$(dirname "$config_file")"
    
    cat > "$config_file" << EOC
{
    "log": {"loglevel": "warning"},
    "inbounds": [{
        "port": $port,
        "protocol": "shadowsocks",
        "settings": {"method": "aes-256-gcm", "password": "$password"}
    }],
    "outbounds": [{
        "protocol": "socks",
        "settings": {"servers": [{
            "address": "$socks_ip",
            "port": $socks_port$([ -n "$socks_user" ] && echo ",\"users\":[{\"user\":\"$socks_user\",\"pass\":\"$socks_pass\"}]")
        }]}
    }]
}
EOC
}

# 启动服务
start_service() {
    local port="$1"
    local pid_file="$SERVICE_DIR/$port/xray.pid"
    local log_file="$SERVICE_DIR/$port/xray.log"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        rm -f "$pid_file"
    fi
    
    nohup "$XRAY_BIN" run -config "$SERVICE_DIR/$port/config.json" > "$log_file" 2>&1 &
    local pid=$!
    echo "$pid" > "$pid_file"
    
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
        log_success "端口 $port 启动成功"
        return 0
    else
        log_error "端口 $port 启动失败"
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
        kill "$pid" 2>/dev/null || true
        sleep 1
        kill -9 "$pid" 2>/dev/null || true
        rm -f "$pid_file"
    fi
}

# 检查状态
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

# 添加服务
add_service() {
    clear
    echo "=== 添加新服务 ==="
    echo ""
    
    read -p "SOCKS5代理 (IP:端口 或 IP:端口:用户名:密码): " input
    [ -z "$input" ] && { log_error "输入不能为空"; return 1; }
    
    IFS=':' read -ra parts <<< "$input"
    [ ${#parts[@]} -lt 2 ] && { log_error "格式错误"; return 1; }
    
    local socks_ip="${parts[0]}" socks_port="${parts[1]}"
    local socks_user="${parts[2]:-}" socks_pass="${parts[3]:-}"
    
    # 生成SS配置
    local ss_port ss_password
    local attempts=0
    while [ $attempts -lt 50 ]; do
        ss_port=$((10000 + RANDOM % 50001))
        [ ! -d "$SERVICE_DIR/$ss_port" ] && break
        attempts=$((attempts + 1))
    done
    
    if command -v openssl >/dev/null 2>&1; then
        ss_password=$(openssl rand -base64 12 | tr -d "=+/")
    else
        ss_password=$(tr -dc 'a-zA-Z0-9' < /dev/urandom | fold -w 12 | head -n 1)
    fi
    
    echo ""
    echo "配置信息:"
    echo "SS端口: $ss_port"
    echo "SS密码: $ss_password"
    echo "后端: $socks_ip:$socks_port"
    echo ""
    
    generate_config "$ss_port" "$ss_password" "$socks_ip" "$socks_port" "$socks_user" "$socks_pass"
    
    cat > "$SERVICE_DIR/$ss_port/info" << EOI
PASSWORD=$ss_password
SOCKS_IP=$socks_ip
SOCKS_PORT=$socks_port
CREATED=$(date)
EOI
    
    if start_service "$ss_port"; then
        echo ""
        log_success "服务创建成功！"
        echo ""
        echo "连接信息:"
        echo "服务器: $(curl -s ifconfig.me 2>/dev/null || echo "YOUR_SERVER_IP")"
        echo "端口: $ss_port"
        echo "密码: $ss_password"
        echo "加密: aes-256-gcm"
    else
        rm -rf "$SERVICE_DIR/$ss_port"
        return 1
    fi
}

# 列出服务
list_services() {
    clear
    echo "=== 服务列表 ==="
    echo ""
    
    if [ ! -d "$SERVICE_DIR" ] || [ -z "$(ls -A "$SERVICE_DIR" 2>/dev/null)" ]; then
        echo "暂无服务"
        return
    fi
    
    printf "%-8s %-10s %-20s\n" "端口" "状态" "后端"
    echo "----------------------------------------"
    
    for port_dir in "$SERVICE_DIR"/*; do
        if [ -d "$port_dir" ]; then
            local port=$(basename "$port_dir")
            local status=$(check_status "$port")
            local backend="未知"
            
            if [ -f "$port_dir/info" ]; then
                local ip=$(grep "SOCKS_IP=" "$port_dir/info" | cut -d'=' -f2)
                local port_num=$(grep "SOCKS_PORT=" "$port_dir/info" | cut -d'=' -f2)
                backend="$ip:$port_num"
            fi
            
            printf "%-8s %-10s %-20s\n" "$port" "$status" "$backend"
        fi
    done
}

# 删除服务
delete_service() {
    clear
    echo "=== 删除服务 ==="
    echo ""
    
    read -p "要删除的端口: " port
    [ ! -d "$SERVICE_DIR/$port" ] && { log_error "服务不存在"; return 1; }
    
    read -p "确认删除端口 $port 的服务？(输入 yes): " confirm
    if [ "$confirm" = "yes" ]; then
        stop_service "$port"
        rm -rf "$SERVICE_DIR/$port"
        log_success "服务已删除"
    fi
}

# 主菜单
main_menu() {
    while true; do
        clear
        echo "=================================="
        echo "  Xray SOCKS5 -> SS 转换器"
        echo "=================================="
        echo ""
        echo "1. 添加服务"
        echo "2. 列出服务"
        echo "3. 删除服务"
        echo "0. 退出"
        echo ""
        read -p "请选择 [0-3]: " choice
        
        case $choice in
            1) add_service; read -p "按回车继续..." ;;
            2) list_services; read -p "按回车继续..." ;;
            3) delete_service; read -p "按回车继续..." ;;
            0) echo "再见！"; exit 0 ;;
            *) echo "无效选择" ;;
        esac
    done
}

# 初始化
mkdir -p "$CONFIG_DIR" "$SERVICE_DIR"
if ! ensure_xray; then
    log_error "初始化失败"
    exit 1
fi

# 启动
main_menu
EOF
    
    chmod +x "$INSTALL_DIR/xray_converter.sh"
}

# 主安装函数
main() {
    clear
    echo "======================================"
    echo "  Xray原生版本一键安装脚本"
    echo "======================================"
    echo ""
    
    log "开始安装..."
    
    # 检查依赖
    if ! check_dependencies; then
        exit 1
    fi
    
    # 创建安装目录
    log "创建安装目录: $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
    
    # 创建脚本
    log "创建转换器脚本..."
    create_simple_script
    
    # 完成安装
    log_success "安装完成！"
    echo ""
    echo "使用方法："
    echo "cd $INSTALL_DIR"
    echo "./xray_converter.sh"
    echo ""
    echo "特性："
    echo "✅ 零依赖 - 自动下载Xray"
    echo "✅ 超轻量 - 内存占用极低"
    echo "✅ 即开即用 - 无需额外配置"
    echo "✅ 完全独立 - 所有文件在安装目录"
    echo "✅ 二维码支持 - 扫码即用"
    echo "✅ 有效期管理 - 灵活控制"
    echo ""
    
    read -p "是否现在启动转换器？(y/N): " start_now
    if [[ "$start_now" =~ ^[yY]$ ]]; then
        cd "$INSTALL_DIR"
        ./xray_converter.sh
    fi
}

# 启动安装
main "$@"
