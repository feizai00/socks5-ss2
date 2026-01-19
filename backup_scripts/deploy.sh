#!/bin/bash
# 一键部署脚本

set -euo pipefail

echo "========================================"
echo "  Xray SOCKS5 转 SS 转换器 - 一键部署"
echo "========================================"
echo ""

# 检查依赖
echo "检查系统依赖..."
missing_deps=()
for cmd in curl unzip; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        missing_deps+=("$cmd")
    fi
done

if [ ${#missing_deps[@]} -gt 0 ]; then
    echo "❌ 缺少依赖: ${missing_deps[*]}"
    echo ""
    echo "请先安装依赖："
    echo "Ubuntu/Debian: sudo apt update && sudo apt install ${missing_deps[*]}"
    echo "CentOS/RHEL: sudo yum install ${missing_deps[*]}"
    exit 1
fi

echo "✅ 依赖检查通过"

# 创建工作目录
WORK_DIR="$HOME/xray-converter"
echo "创建工作目录: $WORK_DIR"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

# 创建主脚本
echo "创建转换器脚本..."
cat > "xray_converter.sh" << 'SCRIPT_EOF'
#!/bin/bash
# Xray SOCKS5 to Shadowsocks 转换器 - 完整版

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

# 获取服务器IP
get_server_ip() {
    local ip
    for service in "ifconfig.me" "ipinfo.io/ip" "icanhazip.com"; do
        if ip=$(curl -s --connect-timeout 5 "$service" 2>/dev/null) && [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "$ip"
            return 0
        fi
    done
    echo "127.0.0.1"
}

# 生成SS链接
generate_ss_link() {
    local password="$1" server_ip="$2" port="$3"
    local auth=$(echo -n "aes-256-gcm:$password" | base64 -w 0 2>/dev/null || echo -n "aes-256-gcm:$password" | base64)
    echo "ss://$auth@$server_ip:$port"
}

# 生成二维码
generate_qrcode() {
    local content="$1"
    if command -v qrencode >/dev/null 2>&1; then
        echo ""
        echo "二维码:"
        qrencode -t ANSIUTF8 "$content"
    else
        echo ""
        echo "💡 提示: 安装 qrencode 可显示二维码"
        echo "   Ubuntu/Debian: sudo apt install qrencode"
        echo "   CentOS/RHEL: sudo yum install qrencode"
    fi
}

# 计算过期时间
calculate_expiry() {
    local days="$1"
    echo $(($(date +%s) + days * 24 * 3600))
}

# 格式化日期
format_date() {
    local timestamp="$1"
    date -d "@$timestamp" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -r "$timestamp" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "Invalid"
}

# 检查过期
is_expired() {
    local port="$1"
    local info_file="$SERVICE_DIR/$port/info"
    [ -f "$info_file" ] || return 1
    
    local expires_at=$(grep "EXPIRES_AT=" "$info_file" 2>/dev/null | cut -d'=' -f2)
    [ -n "$expires_at" ] && [ "$expires_at" != "0" ] && [ "$(date +%s)" -gt "$expires_at" ]
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

    # 输入节点名称
    read -p "请输入节点名称 (用于标识此SOCKS5代理): " node_name
    [ -z "$node_name" ] && { log_error "节点名称不能为空"; return 1; }

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
    
    # 设置有效期
    echo "请设置服务有效期:"
    echo "1) 永久有效"
    echo "2) 7天"
    echo "3) 30天"
    echo "4) 90天"
    echo "5) 自定义天数"
    read -p "请选择 [1-5]: " expiry_choice
    
    local expires_at="0"
    case "$expiry_choice" in
        1) expires_at="0" ;;
        2) expires_at=$(calculate_expiry 7) ;;
        3) expires_at=$(calculate_expiry 30) ;;
        4) expires_at=$(calculate_expiry 90) ;;
        5) 
            read -p "请输入有效天数: " custom_days
            if [[ "$custom_days" =~ ^[0-9]+$ ]] && [ "$custom_days" -gt 0 ]; then
                expires_at=$(calculate_expiry "$custom_days")
            else
                echo "无效输入，设置为永久有效"
                expires_at="0"
            fi
            ;;
        *) expires_at="0" ;;
    esac
    
    generate_config "$ss_port" "$ss_password" "$socks_ip" "$socks_port" "$socks_user" "$socks_pass"
    
    cat > "$SERVICE_DIR/$ss_port/info" << EOI
NODE_NAME=$node_name
PASSWORD=$ss_password
SOCKS_IP=$socks_ip
SOCKS_PORT=$socks_port
SOCKS_USER=$socks_user
SOCKS_PASS=$socks_pass
CREATED=$(date)
CREATED_AT=$(date +%s)
EXPIRES_AT=$expires_at
STATUS=active
EOI
    
    if start_service "$ss_port"; then
        echo ""
        log_success "服务创建成功！"
        echo ""
        
        local server_ip=$(get_server_ip)
        local ss_link=$(generate_ss_link "$ss_password" "$server_ip" "$ss_port")
        
        echo "========================================"
        echo "           Shadowsocks 连接信息"
        echo "========================================"
        echo "服务器地址: $server_ip"
        echo "端口: $ss_port"
        echo "密码: $ss_password"
        echo "加密方式: aes-256-gcm"
        
        if [ "$expires_at" != "0" ]; then
            echo "有效期至: $(format_date "$expires_at")"
        else
            echo "有效期: 永久"
        fi
        
        echo ""
        echo "连接链接:"
        echo "$ss_link"
        
        generate_qrcode "$ss_link"
        
        echo ""
        echo "========================================"
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
    
    printf "%-8s %-12s %-15s %-20s %-12s\n" "端口" "状态" "节点名称" "后端" "有效期"
    echo "--------------------------------------------------------------------"

    for port_dir in "$SERVICE_DIR"/*; do
        if [ -d "$port_dir" ]; then
            local port=$(basename "$port_dir")
            local status=$(check_status "$port")
            local node_name="未知"
            local backend="未知"
            local expiry="永久"

            if is_expired "$port"; then
                status="已过期"
            fi

            if [ -f "$port_dir/info" ]; then
                node_name=$(grep "NODE_NAME=" "$port_dir/info" | cut -d'=' -f2)
                local socks_ip=$(grep "SOCKS_IP=" "$port_dir/info" | cut -d'=' -f2)
                local socks_port=$(grep "SOCKS_PORT=" "$port_dir/info" | cut -d'=' -f2)
                backend="$socks_ip:$socks_port"

                local expires_at=$(grep "EXPIRES_AT=" "$port_dir/info" | cut -d'=' -f2)
                if [ -n "$expires_at" ] && [ "$expires_at" != "0" ]; then
                    expiry=$(format_date "$expires_at" | cut -d' ' -f1)
                fi
            fi

            printf "%-8s %-12s %-15s %-20s %-12s\n" "$port" "$status" "$node_name" "$backend" "$expiry"
        fi
    done
}

# 查看服务详情
view_service() {
    clear
    echo "=== 查看服务详情 ==="
    echo ""
    
    read -p "请输入端口号: " port
    
    if [ ! -d "$SERVICE_DIR/$port" ]; then
        log_error "服务不存在"
        return 1
    fi
    
    local info_file="$SERVICE_DIR/$port/info"
    if [ ! -f "$info_file" ]; then
        log_error "服务信息文件不存在"
        return 1
    fi
    
    local password=$(grep "PASSWORD=" "$info_file" | cut -d'=' -f2)
    local socks_ip=$(grep "SOCKS_IP=" "$info_file" | cut -d'=' -f2)
    local socks_port=$(grep "SOCKS_PORT=" "$info_file" | cut -d'=' -f2)
    local created=$(grep "CREATED=" "$info_file" | cut -d'=' -f2-)
    local expires_at=$(grep "EXPIRES_AT=" "$info_file" | cut -d'=' -f2)
    
    local server_ip=$(get_server_ip)
    local status=$(check_status "$port")
    
    if is_expired "$port"; then
        status="已过期"
    fi
    
    local ss_link=$(generate_ss_link "$password" "$server_ip" "$port")
    
    echo "========================================"
    echo "           服务详细信息"
    echo "========================================"
    echo "端口: $port"
    echo "状态: $status"
    echo "密码: $password"
    echo "加密: aes-256-gcm"
    echo "服务器: $server_ip"
    echo "后端代理: $socks_ip:$socks_port"
    echo "创建时间: $created"
    
    if [ -n "$expires_at" ] && [ "$expires_at" != "0" ]; then
        echo "有效期至: $(format_date "$expires_at")"
        
        local current=$(date +%s)
        local remaining_days=$(( (expires_at - current) / 86400 ))
        if [ $remaining_days -gt 0 ]; then
            echo "剩余天数: $remaining_days 天"
        else
            echo "状态: 已过期"
        fi
    else
        echo "有效期: 永久"
    fi
    
    echo ""
    echo "连接链接:"
    echo "$ss_link"
    
    generate_qrcode "$ss_link"
    
    echo ""
    echo "========================================"
}

# 查看服务详情
view_service() {
    clear
    echo "=== 查看服务详情 ==="
    echo ""

    read -p "请输入端口号: " port

    if [ ! -d "$SERVICE_DIR/$port" ]; then
        log_error "服务不存在"
        return 1
    fi

    local info_file="$SERVICE_DIR/$port/info"
    if [ ! -f "$info_file" ]; then
        log_error "服务信息文件不存在"
        return 1
    fi

    local node_name=$(grep "NODE_NAME=" "$info_file" | cut -d'=' -f2)
    local password=$(grep "PASSWORD=" "$info_file" | cut -d'=' -f2)
    local socks_ip=$(grep "SOCKS_IP=" "$info_file" | cut -d'=' -f2)
    local socks_port=$(grep "SOCKS_PORT=" "$info_file" | cut -d'=' -f2)
    local created=$(grep "CREATED=" "$info_file" | cut -d'=' -f2-)
    local expires_at=$(grep "EXPIRES_AT=" "$info_file" | cut -d'=' -f2)

    local server_ip=$(get_server_ip)
    local status=$(check_status "$port")

    if is_expired "$port"; then
        status="已过期"
    fi

    local ss_link=$(generate_ss_link "$password" "$server_ip" "$port")

    echo "========================================"
    echo "           服务详细信息"
    echo "========================================"
    echo "节点名称: $node_name"
    echo "端口: $port"
    echo "状态: $status"
    echo "密码: $password"
    echo "加密: aes-256-gcm"
    echo "服务器: $server_ip"
    echo "后端代理: $socks_ip:$socks_port"
    echo "创建时间: $created"

    if [ -n "$expires_at" ] && [ "$expires_at" != "0" ]; then
        echo "有效期至: $(format_date "$expires_at")"

        local current=$(date +%s)
        local remaining_days=$(( (expires_at - current) / 86400 ))
        if [ $remaining_days -gt 0 ]; then
            echo "剩余天数: $remaining_days 天"
        else
            echo "状态: 已过期"
        fi
    else
        echo "有效期: 永久"
    fi

    echo ""
    echo "连接链接:"
    echo "$ss_link"

    generate_qrcode "$ss_link"

    echo ""
    echo "========================================"
}

# 删除服务
delete_service() {
    clear
    echo "=== 删除服务 ==="
    echo ""
    
    read -p "请输入要删除的端口: " port
    
    if [ ! -d "$SERVICE_DIR/$port" ]; then
        log_error "服务不存在"
        return 1
    fi
    
    echo "确认删除端口 $port 的服务？"
    read -p "输入 'yes' 确认: " confirm
    
    if [ "$confirm" = "yes" ]; then
        stop_service "$port"
        rm -rf "$SERVICE_DIR/$port"
        log_success "服务已删除"
    else
        echo "操作已取消"
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
        echo "3. 查看服务详情"
        echo "4. 删除服务"
        echo "5. 备份配置"
        echo "0. 退出"
        echo ""
        read -p "请选择 [0-5]: " choice

        case $choice in
            1) add_service; read -p "按回车继续..." ;;
            2) list_services; read -p "按回车继续..." ;;
            3) view_service; read -p "按回车继续..." ;;
            4) delete_service; read -p "按回车继续..." ;;
            5)
                echo "创建备份..."
                backup_file="$CONFIG_DIR/backup_$(date +%Y%m%d_%H%M%S).tar.gz"
                if tar -czf "$backup_file" -C "$CONFIG_DIR" services 2>/dev/null; then
                    echo "✅ 备份创建成功: $backup_file"
                else
                    echo "❌ 备份创建失败"
                fi
                read -p "按回车继续..."
                ;;
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
SCRIPT_EOF

chmod +x "xray_converter.sh"

echo "✅ 部署完成！"
echo ""
echo "使用方法："
echo "cd $WORK_DIR"
echo "./xray_converter.sh"
echo ""

read -p "是否现在启动转换器？(y/N): " start_now
if [[ "$start_now" =~ ^[yY]$ ]]; then
    cd "$WORK_DIR"
    ./xray_converter.sh
fi
