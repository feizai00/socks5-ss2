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
readonly YELLOW='\033[1;33m'
readonly NC='\033[0m'

# 日志函数
log() {
    echo "[$(date '+%H:%M:%S')] $*"
}

log_error() {
    echo -e "${RED}[错误]${NC} $*" >&2
}

log_success() {
    echo -e "${GREEN}[成功]${NC} $*"
}

# 检查并下载Xray
ensure_xray() {
    if [ -f "$XRAY_BIN" ] && [ -x "$XRAY_BIN" ]; then
        log_success "Xray已就绪"
        return 0
    fi
    
    log "正在下载Xray..."
    
    # 检测系统架构
    local arch
    case $(uname -m) in
        x86_64) arch="64" ;;
        aarch64|arm64) arch="arm64-v8a" ;;
        armv7l) arch="arm32-v7a" ;;
        *) 
            log_error "不支持的系统架构: $(uname -m)"
            return 1
            ;;
    esac
    
    # 下载Xray
    local download_url="https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-${arch}.zip"
    local temp_file="/tmp/xray.zip"
    
    if command -v curl >/dev/null 2>&1; then
        curl -L "$download_url" -o "$temp_file" || return 1
    elif command -v wget >/dev/null 2>&1; then
        wget "$download_url" -O "$temp_file" || return 1
    else
        log_error "需要安装 curl 或 wget"
        return 1
    fi
    
    # 解压
    if command -v unzip >/dev/null 2>&1; then
        unzip -j "$temp_file" xray -d "$SCRIPT_DIR" || return 1
    else
        log_error "需要安装 unzip"
        return 1
    fi
    
    chmod +x "$XRAY_BIN"
    rm -f "$temp_file"
    
    log_success "Xray下载完成"
}

# 生成配置文件 (改进版本，增加稳定性配置)
generate_config() {
    local port="$1"
    local password="$2"
    local socks_ip="$3"
    local socks_port="$4"
    local socks_user="$5"
    local socks_pass="$6"

    local config_file="$SERVICE_DIR/$port/config.json"
    mkdir -p "$(dirname "$config_file")"

    # 转义特殊字符
    password=$(echo "$password" | sed 's/"/\\"/g')
    socks_user=$(echo "$socks_user" | sed 's/"/\\"/g')
    socks_pass=$(echo "$socks_pass" | sed 's/"/\\"/g')

    # 生成更稳定的配置
    if [ -n "$socks_user" ] && [ -n "$socks_pass" ]; then
        # 有认证的SOCKS5
        cat > "$config_file" << EOF
{
    "log": {
        "loglevel": "warning",
        "access": "",
        "error": ""
    },
    "inbounds": [
        {
            "port": $port,
            "protocol": "shadowsocks",
            "settings": {
                "method": "aes-256-gcm",
                "password": "$password",
                "network": "tcp,udp"
            },
            "streamSettings": {
                "sockopt": {
                    "tcpKeepAlive": true,
                    "tcpNoDelay": true
                }
            }
        }
    ],
    "outbounds": [
        {
            "protocol": "socks",
            "settings": {
                "servers": [
                    {
                        "address": "$socks_ip",
                        "port": $socks_port,
                        "users": [
                            {
                                "user": "$socks_user",
                                "pass": "$socks_pass"
                            }
                        ]
                    }
                ]
            },
            "streamSettings": {
                "sockopt": {
                    "tcpKeepAlive": true,
                    "tcpNoDelay": true
                }
            }
        },
        {
            "protocol": "freedom",
            "tag": "direct"
        }
    ],
    "routing": {
        "rules": [
            {
                "type": "field",
                "outboundTag": "direct",
                "domain": ["localhost", "127.0.0.1"]
            }
        ]
    }
}
EOF
    else
        # 无认证的SOCKS5
        cat > "$config_file" << EOF
{
    "log": {
        "loglevel": "warning",
        "access": "",
        "error": ""
    },
    "inbounds": [
        {
            "port": $port,
            "protocol": "shadowsocks",
            "settings": {
                "method": "aes-256-gcm",
                "password": "$password",
                "network": "tcp,udp"
            },
            "streamSettings": {
                "sockopt": {
                    "tcpKeepAlive": true,
                    "tcpNoDelay": true
                }
            }
        }
    ],
    "outbounds": [
        {
            "protocol": "socks",
            "settings": {
                "servers": [
                    {
                        "address": "$socks_ip",
                        "port": $socks_port
                    }
                ]
            },
            "streamSettings": {
                "sockopt": {
                    "tcpKeepAlive": true,
                    "tcpNoDelay": true
                }
            }
        },
        {
            "protocol": "freedom",
            "tag": "direct"
        }
    ],
    "routing": {
        "rules": [
            {
                "type": "field",
                "outboundTag": "direct",
                "domain": ["localhost", "127.0.0.1"]
            }
        ]
    }
}
EOF
    fi

    # 验证生成的配置文件
    if command -v jq >/dev/null 2>&1; then
        if ! jq . "$config_file" >/dev/null 2>&1; then
            log_error "生成的配置文件JSON格式错误"
            return 1
        fi
    fi

    log "配置文件生成成功: $config_file"
}

# 启动服务 (改进版本，增加重试和错误处理)
start_service() {
    local port="$1"
    local config_file="$SERVICE_DIR/$port/config.json"
    local pid_file="$SERVICE_DIR/$port/xray.pid"
    local log_file="$SERVICE_DIR/$port/xray.log"
    local retry_count=3

    # 检查配置文件是否存在
    if [ ! -f "$config_file" ]; then
        log_error "端口 $port 配置文件不存在: $config_file"
        return 1
    fi

    # 检查是否已运行
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            log "端口 $port 已在运行 (PID: $pid)"
            return 0
        fi
        rm -f "$pid_file"
    fi

    # 检查端口是否被占用
    if command -v lsof >/dev/null 2>&1; then
        if lsof -i ":$port" >/dev/null 2>&1; then
            log_error "端口 $port 已被其他进程占用"
            lsof -i ":$port"
            return 1
        fi
    fi

    # 验证配置文件格式
    if command -v jq >/dev/null 2>&1; then
        if ! jq . "$config_file" >/dev/null 2>&1; then
            log_error "端口 $port 配置文件JSON格式错误"
            return 1
        fi
    fi

    # 多次尝试启动
    for attempt in $(seq 1 $retry_count); do
        log "尝试启动端口 $port (第 $attempt 次)"

        # 清理旧的日志文件，避免日志过大
        if [ -f "$log_file" ] && [ $(stat -c%s "$log_file" 2>/dev/null || echo 0) -gt 10485760 ]; then
            mv "$log_file" "${log_file}.old"
            touch "$log_file"
        fi

        # 使用更稳定的启动方式 (macOS兼容)
        if command -v setsid >/dev/null 2>&1; then
            # Linux系统使用setsid
            setsid "$XRAY_BIN" run -config "$config_file" > "$log_file" 2>&1 &
        else
            # macOS系统直接启动
            nohup "$XRAY_BIN" run -config "$config_file" > "$log_file" 2>&1 &
        fi
        local pid=$!
        echo "$pid" > "$pid_file"

        # 等待进程稳定
        sleep 2

        # 检查进程是否还在运行
        if kill -0 "$pid" 2>/dev/null; then
            # 再次检查，确保进程真正稳定
            sleep 1
            if kill -0 "$pid" 2>/dev/null; then
                log_success "端口 $port 启动成功 (PID: $pid)"

                # 记录启动时间
                echo "LAST_START=$(date)" >> "$SERVICE_DIR/$port/info"
                echo "LAST_START_AT=$(date +%s)" >> "$SERVICE_DIR/$port/info"

                return 0
            fi
        fi

        # 启动失败，清理PID文件
        rm -f "$pid_file"

        if [ $attempt -lt $retry_count ]; then
            log "端口 $port 启动失败，等待 2 秒后重试..."
            sleep 2
        fi
    done

    log_error "端口 $port 启动失败 (已尝试 $retry_count 次)"

    # 显示错误日志
    if [ -f "$log_file" ]; then
        echo "最近的错误日志:"
        tail -10 "$log_file" | sed 's/^/  /'
    fi

    return 1
}

# 停止服务 (改进版本，确保进程完全终止)
stop_service() {
    local port="$1"
    local pid_file="$SERVICE_DIR/$port/xray.pid"
    local stopped=false

    # 通过PID文件停止
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            log "正在停止端口 $port (PID: $pid)..."

            # 尝试优雅停止
            kill -TERM "$pid" 2>/dev/null || true

            # 等待进程退出
            for i in {1..10}; do
                if ! kill -0 "$pid" 2>/dev/null; then
                    stopped=true
                    break
                fi
                sleep 0.5
            done

            # 如果优雅停止失败，强制终止
            if ! $stopped; then
                log "优雅停止失败，强制终止进程..."
                kill -KILL "$pid" 2>/dev/null || true
                sleep 1

                # 再次检查
                if ! kill -0 "$pid" 2>/dev/null; then
                    stopped=true
                fi
            fi
        else
            stopped=true
        fi
        rm -f "$pid_file"
    fi

    # 通过端口查找并终止进程 (备用方法)
    if ! $stopped && command -v lsof >/dev/null 2>&1; then
        local pids=$(lsof -ti ":$port" 2>/dev/null || true)
        if [ -n "$pids" ]; then
            log "通过端口查找到进程，正在终止..."
            for pid in $pids; do
                kill -TERM "$pid" 2>/dev/null || true
                sleep 1
                kill -KILL "$pid" 2>/dev/null || true
            done
            stopped=true
        fi
    fi

    # 通过进程名查找 (最后的备用方法)
    if ! $stopped; then
        local xray_pids=$(pgrep -f "xray.*$port" 2>/dev/null || true)
        if [ -n "$xray_pids" ]; then
            log "通过进程名查找到相关进程，正在终止..."
            for pid in $xray_pids; do
                kill -TERM "$pid" 2>/dev/null || true
                sleep 1
                kill -KILL "$pid" 2>/dev/null || true
            done
            stopped=true
        fi
    fi

    if $stopped; then
        log "端口 $port 已停止"

        # 记录停止时间
        if [ -f "$SERVICE_DIR/$port/info" ]; then
            echo "LAST_STOP=$(date)" >> "$SERVICE_DIR/$port/info"
            echo "LAST_STOP_AT=$(date +%s)" >> "$SERVICE_DIR/$port/info"
        fi
    else
        log "端口 $port 可能已经停止"
    fi
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

# 生成随机端口
random_port() {
    echo $((10000 + RANDOM % 50001))
}

# 生成随机密码
random_password() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 12 | tr -d "=+/"
    else
        tr -dc 'a-zA-Z0-9' < /dev/urandom | fold -w 12 | head -n 1
    fi
}

# 获取服务器IP
get_server_ip() {
    # 尝试多个服务获取外网IP
    local ip
    local services=(
        "ifconfig.me"
        "ipinfo.io/ip"
        "icanhazip.com"
        "ident.me"
        "api.ipify.org"
        "checkip.amazonaws.com"
    )

    for service in "${services[@]}"; do
        if ip=$(curl -s --connect-timeout 10 --max-time 15 "$service" 2>/dev/null); then
            # 清理返回的IP，去除空白字符
            ip=$(echo "$ip" | tr -d '\n\r\t ' | grep -oE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$')
            if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
                echo "$ip"
                return 0
            fi
        fi
    done

    # 如果所有外网服务都失败，尝试获取本机网卡IP（非127.0.0.1）
    local local_ip
    if command -v ip >/dev/null 2>&1; then
        local_ip=$(ip route get 8.8.8.8 2>/dev/null | awk '{print $7; exit}')
    elif command -v ifconfig >/dev/null 2>&1; then
        local_ip=$(ifconfig 2>/dev/null | grep -E 'inet [0-9]' | grep -v '127.0.0.1' | head -1 | awk '{print $2}' | cut -d: -f2)
    fi

    if [[ "$local_ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] && [ "$local_ip" != "127.0.0.1" ]; then
        echo "$local_ip"
    else
        # 最后的备选方案，提示用户手动输入
        echo "YOUR_SERVER_IP"
    fi
}

# 生成SS链接
generate_ss_link() {
    local password="$1"
    local server_ip="$2"
    local port="$3"
    local node_name="$4"
    local method="aes-256-gcm"

    # 编码认证信息
    local auth=$(echo -n "$method:$password" | base64 -w 0 2>/dev/null || echo -n "$method:$password" | base64)

    # URL编码节点名称
    local encoded_name=$(echo -n "$node_name" | sed 's/ /%20/g' | sed 's/#/%23/g')

    # 生成完整的SS链接
    echo "ss://$auth@$server_ip:$port/?group=#$encoded_name"
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
        echo "提示: 安装 qrencode 可显示二维码"
        echo "Ubuntu/Debian: sudo apt install qrencode"
        echo "CentOS/RHEL: sudo yum install qrencode"
    fi
}

# 计算过期时间戳
calculate_expiry() {
    local days="$1"
    local current=$(date +%s)
    echo $((current + days * 24 * 3600))
}

# 格式化日期
format_date() {
    local timestamp="$1"
    date -d "@$timestamp" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -r "$timestamp" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "Invalid date"
}

# 检查服务是否过期
is_expired() {
    local port="$1"
    local info_file="$SERVICE_DIR/$port/info"

    if [ ! -f "$info_file" ]; then
        return 1
    fi

    local expires_at=$(grep "EXPIRES_AT=" "$info_file" 2>/dev/null | cut -d'=' -f2)
    if [ -z "$expires_at" ] || [ "$expires_at" = "0" ]; then
        return 1  # 永久有效
    fi

    local current=$(date +%s)
    [ "$current" -gt "$expires_at" ]
}

# Web API: 添加服务 (非交互式)
add_service_api() {
    local ss_port="$1"
    local ss_password="$2"
    local node_name="$3"

    log "正在添加服务: 端口=$ss_port, 节点=$node_name"

    # 验证端口
    if ! [[ "$ss_port" =~ ^[0-9]+$ ]] || [ "$ss_port" -lt 1024 ] || [ "$ss_port" -gt 65535 ]; then
        log_error "端口必须是1024-65535之间的数字"
        return 1
    fi

    # 检查端口是否已被使用
    if [ -d "$SERVICE_DIR/$ss_port" ]; then
        log_error "端口 $ss_port 已被使用"
        return 1
    fi

    # 验证密码
    if [ -z "$ss_password" ]; then
        log_error "密码不能为空"
        return 1
    fi

    # 创建必要的目录
    mkdir -p "$CONFIG_DIR" "$SERVICE_DIR"

    # 创建服务目录
    local service_dir="$SERVICE_DIR/$ss_port"
    mkdir -p "$service_dir"

    # 生成Xray配置
    local config_file="$service_dir/config.json"
    cat > "$config_file" << EOF
{
    "log": {
        "loglevel": "warning"
    },
    "inbounds": [
        {
            "port": $ss_port,
            "protocol": "shadowsocks",
            "settings": {
                "method": "chacha20-ietf-poly1305",
                "password": "$ss_password"
            }
        }
    ],
    "outbounds": [
        {
            "protocol": "freedom",
            "settings": {}
        }
    ]
}
EOF

    # 保存服务信息
    local info_file="$service_dir/info.txt"
    cat > "$info_file" << EOF
节点名称: $node_name
端口: $ss_port
密码: $ss_password
协议: Shadowsocks
加密方式: chacha20-ietf-poly1305
创建时间: $(date '+%Y-%m-%d %H:%M:%S')
有效期: 永久
状态: 已创建
EOF

    echo "服务创建成功: $node_name (端口: $ss_port)"
    return 0
}

# 添加服务
add_service() {
    clear
    echo "=== 添加新服务 ==="
    echo ""

    # 输入节点名称
    read -p "请输入节点名称 (用于标识此SOCKS5代理): " node_name
    if [ -z "$node_name" ]; then
        log_error "节点名称不能为空"
        return 1
    fi

    read -p "SOCKS5代理地址 (格式: IP:端口 或 IP:端口:用户名:密码): " socks_input

    if [ -z "$socks_input" ]; then
        log_error "输入不能为空"
        return 1
    fi
    
    # 解析输入
    IFS=':' read -ra parts <<< "$socks_input"
    
    if [ ${#parts[@]} -lt 2 ]; then
        log_error "格式错误"
        return 1
    fi
    
    local socks_ip="${parts[0]}"
    local socks_port="${parts[1]}"
    local socks_user="${parts[2]:-}"
    local socks_pass="${parts[3]:-}"
    
    # 生成SS配置
    local ss_port
    local attempts=0
    while [ $attempts -lt 50 ]; do
        ss_port=$(random_port)
        if [ ! -d "$SERVICE_DIR/$ss_port" ]; then
            break
        fi
        attempts=$((attempts + 1))
    done
    
    local ss_password=$(random_password)

    echo ""
    echo "配置信息:"
    echo "Shadowsocks 端口: $ss_port"
    echo "Shadowsocks 密码: $ss_password"
    echo "SOCKS5 后端: $socks_ip:$socks_port"
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
        *)
            echo "无效选择，设置为永久有效"
            expires_at="0"
            ;;
    esac

    if [ "$expires_at" != "0" ]; then
        echo "服务将于 $(format_date "$expires_at") 过期"
    else
        echo "服务永久有效"
    fi
    echo ""
    
    # 生成配置
    generate_config "$ss_port" "$ss_password" "$socks_ip" "$socks_port" "$socks_user" "$socks_pass"
    
    # 保存信息
    cat > "$SERVICE_DIR/$ss_port/info" << EOF
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
EOF
    
    # 启动服务
    if start_service "$ss_port"; then
        echo ""
        log_success "服务创建成功！"
        echo ""

        # 获取服务器IP
        local server_ip=$(get_server_ip)

        # 使用用户输入的节点名称（已在函数开始时获取）
        # node_name 变量已在第323行通过 read 命令获取

        # 生成SS链接
        local ss_link=$(generate_ss_link "$ss_password" "$server_ip" "$ss_port" "$node_name")

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

        # 如果IP是占位符，提示用户替换
        if [ "$server_ip" = "YOUR_SERVER_IP" ]; then
            echo ""
            echo "⚠️  注意：无法自动获取服务器外网IP，请手动替换链接中的 'YOUR_SERVER_IP' 为您的真实服务器IP地址"
        fi

        # 生成二维码
        generate_qrcode "$ss_link"

        echo ""
        echo "========================================"
        echo "提示: 请保存上述信息，用于配置客户端"
        echo "========================================"
    else
        log_error "服务启动失败"
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

    printf "%-8s %-12s %-15s %-20s %-12s %s\n" "端口" "状态" "节点名称" "后端" "有效期" "创建时间"
    echo "--------------------------------------------------------------------------------"

    for port_dir in "$SERVICE_DIR"/*; do
        if [ -d "$port_dir" ]; then
            local port=$(basename "$port_dir")
            local status=$(check_status "$port")
            local node_name="未知"
            local backend="未知"
            local created="未知"
            local expiry="永久"

            # 检查是否过期
            if is_expired "$port"; then
                status="已过期"
            fi

            if [ -f "$port_dir/info" ]; then
                node_name=$(grep "NODE_NAME=" "$port_dir/info" | cut -d'=' -f2)
                local socks_ip=$(grep "SOCKS_IP=" "$port_dir/info" | cut -d'=' -f2)
                local socks_port=$(grep "SOCKS_PORT=" "$port_dir/info" | cut -d'=' -f2)
                backend="$socks_ip:$socks_port"
                created=$(grep "CREATED=" "$port_dir/info" | cut -d'=' -f2- | cut -d' ' -f1-2)

                local expires_at=$(grep "EXPIRES_AT=" "$port_dir/info" | cut -d'=' -f2)
                if [ -n "$expires_at" ] && [ "$expires_at" != "0" ]; then
                    expiry=$(format_date "$expires_at" | cut -d' ' -f1)
                fi
            fi

            printf "%-8s %-12s %-15s %-20s %-12s %s\n" "$port" "$status" "$node_name" "$backend" "$expiry" "$created"
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

    # 读取服务信息
    local node_name=$(grep "NODE_NAME=" "$info_file" | cut -d'=' -f2)
    local password=$(grep "PASSWORD=" "$info_file" | cut -d'=' -f2)
    local socks_ip=$(grep "SOCKS_IP=" "$info_file" | cut -d'=' -f2)
    local socks_port=$(grep "SOCKS_PORT=" "$info_file" | cut -d'=' -f2)
    local created=$(grep "CREATED=" "$info_file" | cut -d'=' -f2-)
    local expires_at=$(grep "EXPIRES_AT=" "$info_file" | cut -d'=' -f2)

    # 获取服务器IP和状态
    local server_ip=$(get_server_ip)
    local status=$(check_status "$port")

    # 检查是否过期
    if is_expired "$port"; then
        status="已过期"
    fi

    # 生成SS链接（使用节点名称）
    local ss_link=$(generate_ss_link "$password" "$server_ip" "$port" "$node_name")

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

        # 计算剩余天数
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

    # 如果IP是占位符，提示用户替换
    if [ "$server_ip" = "YOUR_SERVER_IP" ]; then
        echo ""
        echo "⚠️  注意：无法自动获取服务器外网IP，请手动替换链接中的 'YOUR_SERVER_IP' 为您的真实服务器IP地址"
    fi

    # 生成二维码
    generate_qrcode "$ss_link"

    echo ""
    echo "========================================"
}

# 续费服务
renew_service() {
    clear
    echo "=== 续费服务 ==="
    echo ""

    # 列出所有服务，特别标注过期和即将过期的
    if [ ! -d "$SERVICE_DIR" ] || [ -z "$(ls -A "$SERVICE_DIR" 2>/dev/null)" ]; then
        echo "暂无服务"
        return
    fi

    echo "服务列表 (标注过期状态):"
    echo ""
    printf "%-8s %-15s %-12s %-20s %s\n" "端口" "节点名称" "状态" "有效期" "剩余天数"
    echo "------------------------------------------------------------------------"

    local services=()
    local current=$(date +%s)

    for port_dir in "$SERVICE_DIR"/*; do
        if [ -d "$port_dir" ]; then
            local port=$(basename "$port_dir")
            local node_name="未知"
            local expiry="永久"
            local remaining="永久"
            local status_text="正常"

            if [ -f "$port_dir/info" ]; then
                node_name=$(grep "NODE_NAME=" "$port_dir/info" | cut -d'=' -f2)
                local expires_at=$(grep "EXPIRES_AT=" "$port_dir/info" | cut -d'=' -f2)

                if [ -n "$expires_at" ] && [ "$expires_at" != "0" ]; then
                    expiry=$(format_date "$expires_at" | cut -d' ' -f1)
                    local remaining_seconds=$((expires_at - current))
                    local remaining_days=$((remaining_seconds / 86400))

                    if [ $remaining_days -lt 0 ]; then
                        remaining="已过期"
                        status_text="已过期"
                    elif [ $remaining_days -eq 0 ]; then
                        remaining="今天到期"
                        status_text="今天到期"
                    elif [ $remaining_days -le 7 ]; then
                        remaining="${remaining_days}天"
                        status_text="即将过期"
                    else
                        remaining="${remaining_days}天"
                    fi
                fi
            fi

            services+=("$port")
            printf "%-8s %-15s %-12s %-20s %s\n" "$port" "$node_name" "$status_text" "$expiry" "$remaining"
        fi
    done

    echo ""
    read -p "请输入要续费的端口号: " port

    if [ ! -d "$SERVICE_DIR/$port" ]; then
        log_error "服务不存在"
        return 1
    fi

    local info_file="$SERVICE_DIR/$port/info"
    if [ ! -f "$info_file" ]; then
        log_error "服务信息文件不存在"
        return 1
    fi

    # 显示当前服务信息
    local node_name=$(grep "NODE_NAME=" "$info_file" | cut -d'=' -f2)
    local current_expires=$(grep "EXPIRES_AT=" "$info_file" | cut -d'=' -f2)

    echo ""
    echo "当前服务信息:"
    echo "节点名称: $node_name"
    echo "端口: $port"

    if [ -n "$current_expires" ] && [ "$current_expires" != "0" ]; then
        echo "当前有效期至: $(format_date "$current_expires")"
        local remaining_seconds=$((current_expires - current))
        local remaining_days=$((remaining_seconds / 86400))
        if [ $remaining_days -lt 0 ]; then
            echo "状态: 已过期 $((0 - remaining_days)) 天"
        elif [ $remaining_days -eq 0 ]; then
            echo "状态: 今天到期"
        else
            echo "剩余: $remaining_days 天"
        fi
    else
        echo "当前有效期: 永久"
    fi

    echo ""
    echo "请选择续费时长:"
    echo "1) 永久有效"
    echo "2) 7天"
    echo "3) 30天"
    echo "4) 90天"
    echo "5) 自定义天数"
    read -p "请选择 [1-5]: " renew_choice

    local new_expires="0"
    local renew_description=""

    case "$renew_choice" in
        1)
            new_expires="0"
            renew_description="永久有效"
            ;;
        2)
            new_expires=$(calculate_expiry 7)
            renew_description="7天"
            ;;
        3)
            new_expires=$(calculate_expiry 30)
            renew_description="30天"
            ;;
        4)
            new_expires=$(calculate_expiry 90)
            renew_description="90天"
            ;;
        5)
            read -p "请输入续费天数: " custom_days
            if [[ "$custom_days" =~ ^[0-9]+$ ]] && [ "$custom_days" -gt 0 ]; then
                new_expires=$(calculate_expiry "$custom_days")
                renew_description="${custom_days}天"
            else
                log_error "无效输入"
                return 1
            fi
            ;;
        *)
            log_error "无效选择"
            return 1
            ;;
    esac

    # 如果当前是永久有效，询问是否确认改为有限期
    if [ "$current_expires" = "0" ] && [ "$new_expires" != "0" ]; then
        echo ""
        echo "警告: 当前服务是永久有效，续费后将变为有限期服务"
        read -p "确认继续？(y/N): " confirm_change
        if [[ ! "$confirm_change" =~ ^[yY]$ ]]; then
            echo "操作已取消"
            return 0
        fi
    fi

    # 如果当前有有效期且未过期，询问是否从当前到期时间开始计算
    if [ "$current_expires" != "0" ] && [ "$new_expires" != "0" ]; then
        local current_time=$(date +%s)
        if [ "$current_expires" -gt "$current_time" ]; then
            echo ""
            echo "当前服务尚未过期，续费方式:"
            echo "1) 从当前到期时间开始计算 (推荐)"
            echo "2) 从现在开始重新计算"
            read -p "请选择 [1-2]: " extend_method

            if [ "$extend_method" = "1" ]; then
                # 从当前到期时间开始计算
                case "$renew_choice" in
                    1) new_expires="0" ;;
                    2) new_expires=$((current_expires + 7 * 24 * 3600)) ;;
                    3) new_expires=$((current_expires + 30 * 24 * 3600)) ;;
                    4) new_expires=$((current_expires + 90 * 24 * 3600)) ;;
                    5) new_expires=$((current_expires + custom_days * 24 * 3600)) ;;
                esac
            fi
        fi
    fi

    echo ""
    echo "续费信息确认:"
    echo "服务: $node_name (端口 $port)"
    echo "续费时长: $renew_description"
    if [ "$new_expires" != "0" ]; then
        echo "新的到期时间: $(format_date "$new_expires")"
    else
        echo "新的到期时间: 永久有效"
    fi
    echo ""
    read -p "确认续费？(y/N): " confirm

    if [[ ! "$confirm" =~ ^[yY]$ ]]; then
        echo "操作已取消"
        return 0
    fi

    # 更新服务信息
    sed -i "s/^EXPIRES_AT=.*/EXPIRES_AT=$new_expires/" "$info_file"

    # 添加续费记录
    echo "RENEWED=$(date)" >> "$info_file"
    echo "RENEWED_AT=$(date +%s)" >> "$info_file"
    echo "RENEWED_TO=$renew_description" >> "$info_file"

    log_success "续费成功！"
    echo ""
    echo "服务: $node_name"
    echo "端口: $port"
    if [ "$new_expires" != "0" ]; then
        echo "新的到期时间: $(format_date "$new_expires")"
    else
        echo "有效期: 永久"
    fi
}

# 编辑服务
edit_service() {
    clear
    echo "=== 编辑服务 ==="
    echo ""

    # 列出所有服务
    if [ ! -d "$SERVICE_DIR" ] || [ -z "$(ls -A "$SERVICE_DIR" 2>/dev/null)" ]; then
        echo "暂无服务可编辑"
        return
    fi

    echo "现有服务列表:"
    echo ""
    printf "%-8s %-15s %-12s %-20s %s\n" "端口" "节点名称" "状态" "后端代理" "有效期"
    echo "------------------------------------------------------------------------"

    for port_dir in "$SERVICE_DIR"/*; do
        if [ -d "$port_dir" ]; then
            local port=$(basename "$port_dir")
            local status=$(check_status "$port")
            local node_name="未知"
            local backend="未知"
            local expiry="永久"

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

            printf "%-8s %-15s %-12s %-20s %s\n" "$port" "$node_name" "$status" "$backend" "$expiry"
        fi
    done

    echo ""
    read -p "请输入要编辑的端口号: " port

    if [ ! -d "$SERVICE_DIR/$port" ]; then
        log_error "服务不存在"
        return 1
    fi

    local info_file="$SERVICE_DIR/$port/info"
    if [ ! -f "$info_file" ]; then
        log_error "服务信息文件不存在"
        return 1
    fi

    # 读取当前配置
    local current_node_name=$(grep "NODE_NAME=" "$info_file" | cut -d'=' -f2)
    local current_socks_ip=$(grep "SOCKS_IP=" "$info_file" | cut -d'=' -f2)
    local current_socks_port=$(grep "SOCKS_PORT=" "$info_file" | cut -d'=' -f2)
    local current_socks_user=$(grep "SOCKS_USER=" "$info_file" | cut -d'=' -f2)
    local current_socks_pass=$(grep "SOCKS_PASS=" "$info_file" | cut -d'=' -f2)
    local current_password=$(grep "PASSWORD=" "$info_file" | cut -d'=' -f2)
    local current_expires_at=$(grep "EXPIRES_AT=" "$info_file" | cut -d'=' -f2)

    echo ""
    echo "当前配置:"
    echo "节点名称: $current_node_name"
    echo "SOCKS5代理: $current_socks_ip:$current_socks_port"
    if [ -n "$current_socks_user" ]; then
        echo "认证信息: $current_socks_user:$current_socks_pass"
    else
        echo "认证信息: 无"
    fi
    echo "SS密码: $current_password"
    if [ "$current_expires_at" != "0" ]; then
        echo "有效期至: $(format_date "$current_expires_at")"
    else
        echo "有效期: 永久"
    fi

    echo ""
    echo "请选择要编辑的项目:"
    echo "1) 节点名称"
    echo "2) SOCKS5代理信息"
    echo "3) SS密码"
    echo "4) 有效期"
    echo "5) 全部重新配置"
    echo "0) 返回主菜单"
    echo ""
    read -p "请选择 [0-5]: " edit_choice

    case "$edit_choice" in
        1)
            # 编辑节点名称
            echo ""
            echo "当前节点名称: $current_node_name"
            read -p "请输入新的节点名称 (回车保持不变): " new_node_name

            if [ -n "$new_node_name" ]; then
                sed -i "s/^NODE_NAME=.*/NODE_NAME=$new_node_name/" "$info_file"
                log_success "节点名称已更新为: $new_node_name"
            else
                echo "节点名称保持不变"
            fi
            ;;
        2)
            # 编辑SOCKS5代理信息
            echo ""
            echo "当前SOCKS5代理: $current_socks_ip:$current_socks_port"
            if [ -n "$current_socks_user" ]; then
                echo "当前认证: $current_socks_user:$current_socks_pass"
            fi
            echo ""
            read -p "请输入新的SOCKS5代理 (格式: IP:端口 或 IP:端口:用户名:密码): " new_socks_input

            if [ -n "$new_socks_input" ]; then
                # 解析输入
                IFS=':' read -ra parts <<< "$new_socks_input"

                if [ ${#parts[@]} -lt 2 ]; then
                    log_error "格式错误"
                    return 1
                fi

                local new_socks_ip="${parts[0]}"
                local new_socks_port="${parts[1]}"
                local new_socks_user="${parts[2]:-}"
                local new_socks_pass="${parts[3]:-}"

                # 更新配置文件
                generate_config "$port" "$current_password" "$new_socks_ip" "$new_socks_port" "$new_socks_user" "$new_socks_pass"

                # 更新info文件
                sed -i "s/^SOCKS_IP=.*/SOCKS_IP=$new_socks_ip/" "$info_file"
                sed -i "s/^SOCKS_PORT=.*/SOCKS_PORT=$new_socks_port/" "$info_file"
                sed -i "s/^SOCKS_USER=.*/SOCKS_USER=$new_socks_user/" "$info_file"
                sed -i "s/^SOCKS_PASS=.*/SOCKS_PASS=$new_socks_pass/" "$info_file"

                # 重启服务
                echo "正在重启服务以应用新配置..."
                stop_service "$port"
                sleep 2
                if start_service "$port"; then
                    log_success "SOCKS5代理信息已更新并重启服务"
                else
                    log_error "服务重启失败，请检查新的代理配置"
                fi
            else
                echo "SOCKS5代理信息保持不变"
            fi
            ;;
        3)
            # 编辑SS密码
            echo ""
            echo "当前SS密码: $current_password"
            read -p "请输入新的SS密码 (回车自动生成): " new_password

            if [ -z "$new_password" ]; then
                new_password=$(random_password)
                echo "自动生成新密码: $new_password"
            fi

            # 更新配置文件
            generate_config "$port" "$new_password" "$current_socks_ip" "$current_socks_port" "$current_socks_user" "$current_socks_pass"

            # 更新info文件
            sed -i "s/^PASSWORD=.*/PASSWORD=$new_password/" "$info_file"

            # 重启服务
            echo "正在重启服务以应用新密码..."
            stop_service "$port"
            sleep 2
            if start_service "$port"; then
                log_success "SS密码已更新并重启服务"
                echo ""
                echo "新的连接信息:"
                local server_ip=$(get_server_ip)
                echo "服务器: $server_ip"
                echo "端口: $port"
                echo "密码: $new_password"
                echo "加密: aes-256-gcm"
            else
                log_error "服务重启失败"
            fi
            ;;
        4)
            # 编辑有效期
            echo ""
            if [ "$current_expires_at" != "0" ]; then
                echo "当前有效期至: $(format_date "$current_expires_at")"
            else
                echo "当前有效期: 永久"
            fi
            echo ""
            echo "请选择新的有效期:"
            echo "1) 永久有效"
            echo "2) 7天"
            echo "3) 30天"
            echo "4) 90天"
            echo "5) 自定义天数"
            read -p "请选择 [1-5]: " expiry_choice

            local new_expires="0"
            case "$expiry_choice" in
                1) new_expires="0" ;;
                2) new_expires=$(calculate_expiry 7) ;;
                3) new_expires=$(calculate_expiry 30) ;;
                4) new_expires=$(calculate_expiry 90) ;;
                5)
                    read -p "请输入有效天数: " custom_days
                    if [[ "$custom_days" =~ ^[0-9]+$ ]] && [ "$custom_days" -gt 0 ]; then
                        new_expires=$(calculate_expiry "$custom_days")
                    else
                        log_error "无效输入"
                        return 1
                    fi
                    ;;
                *)
                    log_error "无效选择"
                    return 1
                    ;;
            esac

            # 更新有效期
            sed -i "s/^EXPIRES_AT=.*/EXPIRES_AT=$new_expires/" "$info_file"
            echo "EDITED=$(date)" >> "$info_file"
            echo "EDITED_AT=$(date +%s)" >> "$info_file"

            if [ "$new_expires" != "0" ]; then
                log_success "有效期已更新至: $(format_date "$new_expires")"
            else
                log_success "有效期已设置为永久"
            fi
            ;;
        5)
            # 全部重新配置
            echo ""
            echo "⚠️  警告: 这将重新配置所有参数，包括生成新的SS密码"
            read -p "确认继续？(y/N): " confirm_all

            if [[ ! "$confirm_all" =~ ^[yY]$ ]]; then
                echo "操作已取消"
                return 0
            fi

            # 重新输入所有配置
            echo ""
            read -p "节点名称 [$current_node_name]: " new_node_name
            new_node_name=${new_node_name:-$current_node_name}

            echo ""
            read -p "SOCKS5代理 (格式: IP:端口 或 IP:端口:用户名:密码): " new_socks_input

            if [ -z "$new_socks_input" ]; then
                log_error "SOCKS5代理信息不能为空"
                return 1
            fi

            # 解析输入
            IFS=':' read -ra parts <<< "$new_socks_input"

            if [ ${#parts[@]} -lt 2 ]; then
                log_error "格式错误"
                return 1
            fi

            local new_socks_ip="${parts[0]}"
            local new_socks_port="${parts[1]}"
            local new_socks_user="${parts[2]:-}"
            local new_socks_pass="${parts[3]:-}"

            # 生成新密码
            local new_password=$(random_password)

            # 设置有效期
            echo ""
            echo "请设置有效期:"
            echo "1) 永久有效"
            echo "2) 7天"
            echo "3) 30天"
            echo "4) 90天"
            echo "5) 自定义天数"
            read -p "请选择 [1-5]: " expiry_choice

            local new_expires="0"
            case "$expiry_choice" in
                1) new_expires="0" ;;
                2) new_expires=$(calculate_expiry 7) ;;
                3) new_expires=$(calculate_expiry 30) ;;
                4) new_expires=$(calculate_expiry 90) ;;
                5)
                    read -p "请输入有效天数: " custom_days
                    if [[ "$custom_days" =~ ^[0-9]+$ ]] && [ "$custom_days" -gt 0 ]; then
                        new_expires=$(calculate_expiry "$custom_days")
                    else
                        log_error "无效输入"
                        return 1
                    fi
                    ;;
                *)
                    log_error "无效选择"
                    return 1
                    ;;
            esac

            # 更新所有配置
            generate_config "$port" "$new_password" "$new_socks_ip" "$new_socks_port" "$new_socks_user" "$new_socks_pass"

            # 更新info文件
            cat > "$info_file" << EOF
NODE_NAME=$new_node_name
PASSWORD=$new_password
SOCKS_IP=$new_socks_ip
SOCKS_PORT=$new_socks_port
SOCKS_USER=$new_socks_user
SOCKS_PASS=$new_socks_pass
CREATED=$(grep "CREATED=" "$info_file" | cut -d'=' -f2-)
CREATED_AT=$(grep "CREATED_AT=" "$info_file" | cut -d'=' -f2)
EXPIRES_AT=$new_expires
STATUS=active
EDITED=$(date)
EDITED_AT=$(date +%s)
EOF

            # 重启服务
            echo ""
            echo "正在重启服务以应用新配置..."
            stop_service "$port"
            sleep 2
            if start_service "$port"; then
                log_success "服务配置已全部更新并重启"
                echo ""
                echo "新的连接信息:"
                local server_ip=$(get_server_ip)
                echo "节点名称: $new_node_name"
                echo "服务器: $server_ip"
                echo "端口: $port"
                echo "密码: $new_password"
                echo "加密: aes-256-gcm"
                if [ "$new_expires" != "0" ]; then
                    echo "有效期至: $(format_date "$new_expires")"
                else
                    echo "有效期: 永久"
                fi
            else
                log_error "服务重启失败，请检查配置"
            fi
            ;;
        0)
            echo "返回主菜单"
            return 0
            ;;
        *)
            log_error "无效选择"
            ;;
    esac
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

# 备份配置
backup_config() {
    clear
    echo "=== 备份配置 ==="
    echo ""

    if [ ! -d "$SERVICE_DIR" ] || [ -z "$(ls -A "$SERVICE_DIR" 2>/dev/null)" ]; then
        log_error "没有可备份的服务"
        return 1
    fi

    local backup_name="xray_backup_$(date +%Y%m%d_%H%M%S).tar.gz"
    local backup_path="$CONFIG_DIR/$backup_name"

    echo "正在创建备份..."
    if tar -czf "$backup_path" -C "$CONFIG_DIR" services; then
        log_success "备份创建成功"
        echo ""
        echo "备份文件: $backup_path"
        echo "备份大小: $(du -h "$backup_path" | cut -f1)"
        echo "包含服务: $(ls "$SERVICE_DIR" | wc -l) 个"
        echo ""
        echo "备份文件可以复制到其他位置保存："
        echo "cp \"$backup_path\" /path/to/safe/location/"
    else
        log_error "备份创建失败"
        return 1
    fi
}

# 恢复配置
restore_config() {
    clear
    echo "=== 恢复配置 ==="
    echo ""

    # 列出可用的备份文件
    local backup_files=()
    if [ -d "$CONFIG_DIR" ]; then
        while IFS= read -r -d '' file; do
            backup_files+=("$file")
        done < <(find "$CONFIG_DIR" -name "xray_backup_*.tar.gz" -print0 2>/dev/null)
    fi

    # 检查是否有备份文件
    if [ ${#backup_files[@]} -eq 0 ]; then
        echo "未找到备份文件"
        echo ""
        echo "您可以："
        echo "1. 将备份文件复制到: $CONFIG_DIR/"
        echo "2. 手动指定备份文件路径"
        echo ""
        read -p "是否手动指定备份文件路径？(y/N): " manual_path

        if [[ "$manual_path" =~ ^[yY]$ ]]; then
            read -p "请输入备份文件完整路径: " backup_file
            if [ ! -f "$backup_file" ]; then
                log_error "备份文件不存在"
                return 1
            fi
        else
            return 1
        fi
    else
        echo "找到以下备份文件："
        echo ""
        for i in "${!backup_files[@]}"; do
            local file="${backup_files[$i]}"
            local filename=$(basename "$file")
            local size=$(du -h "$file" | cut -f1)
            local date=$(echo "$filename" | sed 's/xray_backup_\([0-9]\{8\}_[0-9]\{6\}\).*/\1/' | sed 's/_/ /')
            printf "%d) %s (%s) - %s\n" $((i+1)) "$filename" "$size" "$date"
        done
        echo ""
        read -p "请选择要恢复的备份 [1-${#backup_files[@]}]: " choice

        if ! [[ "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -lt 1 ] || [ "$choice" -gt ${#backup_files[@]} ]; then
            log_error "无效选择"
            return 1
        fi

        backup_file="${backup_files[$((choice-1))]}"
    fi

    echo ""
    echo "警告: 恢复操作将覆盖当前所有服务配置！"
    echo "备份文件: $(basename "$backup_file")"
    echo ""
    read -p "确认恢复？输入 'yes' 继续: " confirm

    if [ "$confirm" != "yes" ]; then
        echo "操作已取消"
        return 0
    fi

    # 停止所有当前服务
    echo ""
    echo "正在停止当前服务..."
    if [ -d "$SERVICE_DIR" ]; then
        for port_dir in "$SERVICE_DIR"/*; do
            if [ -d "$port_dir" ]; then
                local port=$(basename "$port_dir")
                stop_service "$port"
            fi
        done
    fi

    # 备份当前配置（以防恢复失败）
    if [ -d "$SERVICE_DIR" ] && [ -n "$(ls -A "$SERVICE_DIR" 2>/dev/null)" ]; then
        local current_backup="$CONFIG_DIR/current_backup_$(date +%Y%m%d_%H%M%S).tar.gz"
        tar -czf "$current_backup" -C "$CONFIG_DIR" services 2>/dev/null
        echo "当前配置已备份到: $current_backup"
    fi

    # 删除当前服务目录
    rm -rf "$SERVICE_DIR"

    # 恢复备份
    echo "正在恢复配置..."
    if tar -xzf "$backup_file" -C "$CONFIG_DIR"; then
        log_success "配置恢复成功"

        # 启动恢复的服务
        echo ""
        echo "正在启动服务..."
        local started=0
        local failed=0

        for port_dir in "$SERVICE_DIR"/*; do
            if [ -d "$port_dir" ]; then
                local port=$(basename "$port_dir")
                if start_service "$port"; then
                    started=$((started + 1))
                else
                    failed=$((failed + 1))
                fi
            fi
        done

        echo ""
        echo "恢复完成："
        echo "- 成功启动: $started 个服务"
        if [ $failed -gt 0 ]; then
            echo "- 启动失败: $failed 个服务"
        fi
    else
        log_error "配置恢复失败"
        return 1
    fi
}

# 管理备份文件
manage_backups() {
    clear
    echo "=== 管理备份文件 ==="
    echo ""

    # 列出备份文件
    local backup_files=()
    if [ -d "$CONFIG_DIR" ]; then
        while IFS= read -r -d '' file; do
            backup_files+=("$file")
        done < <(find "$CONFIG_DIR" -name "*backup*.tar.gz" -print0 2>/dev/null)
    fi

    if [ ${#backup_files[@]} -eq 0 ]; then
        echo "未找到备份文件"
        return 0
    fi

    echo "备份文件列表："
    echo ""
    local total_size=0
    for i in "${!backup_files[@]}"; do
        local file="${backup_files[$i]}"
        local filename=$(basename "$file")
        local size_kb=$(du -k "$file" | cut -f1)
        local size_human=$(du -h "$file" | cut -f1)
        local date=$(stat -c %y "$file" 2>/dev/null | cut -d' ' -f1,2 | cut -d'.' -f1)

        printf "%d) %s (%s) - %s\n" $((i+1)) "$filename" "$size_human" "$date"
        total_size=$((total_size + size_kb))
    done

    echo ""
    echo "总计: ${#backup_files[@]} 个文件，$(echo "scale=1; $total_size/1024" | bc 2>/dev/null || echo $((total_size/1024)))MB"
    echo ""
    echo "操作选项："
    echo "1) 删除指定备份"
    echo "2) 清理旧备份（保留最新5个）"
    echo "3) 返回主菜单"
    echo ""
    read -p "请选择操作 [1-3]: " action

    case "$action" in
        1)
            read -p "请输入要删除的备份编号 [1-${#backup_files[@]}]: " del_choice
            if [[ "$del_choice" =~ ^[0-9]+$ ]] && [ "$del_choice" -ge 1 ] && [ "$del_choice" -le ${#backup_files[@]} ]; then
                local del_file="${backup_files[$((del_choice-1))]}"
                read -p "确认删除 $(basename "$del_file")？(y/N): " confirm
                if [[ "$confirm" =~ ^[yY]$ ]]; then
                    rm -f "$del_file"
                    log_success "备份文件已删除"
                fi
            else
                log_error "无效选择"
            fi
            ;;
        2)
            if [ ${#backup_files[@]} -gt 5 ]; then
                # 按时间排序，删除最旧的
                local sorted_files=($(printf '%s\n' "${backup_files[@]}" | sort -t_ -k3,3))
                local to_delete=$((${#sorted_files[@]} - 5))

                echo "将删除 $to_delete 个旧备份文件"
                read -p "确认清理？(y/N): " confirm
                if [[ "$confirm" =~ ^[yY]$ ]]; then
                    for ((i=0; i<to_delete; i++)); do
                        rm -f "${sorted_files[$i]}"
                    done
                    log_success "已清理 $to_delete 个旧备份文件"
                fi
            else
                echo "备份文件数量不超过5个，无需清理"
            fi
            ;;
        3)
            return 0
            ;;
        *)
            log_error "无效选择"
            ;;
    esac
}

# 诊断服务问题
diagnose_service() {
    clear
    echo "=== 服务诊断 ==="
    echo ""

    if [ ! -d "$SERVICE_DIR" ] || [ -z "$(ls -A "$SERVICE_DIR" 2>/dev/null)" ]; then
        echo "暂无服务需要诊断"
        return
    fi

    echo "正在诊断所有服务..."
    echo ""

    for port_dir in "$SERVICE_DIR"/*; do
        if [ -d "$port_dir" ]; then
            local port=$(basename "$port_dir")
            local pid_file="$port_dir/xray.pid"
            local log_file="$port_dir/xray.log"
            local config_file="$port_dir/config.json"

            echo "=== 端口 $port ==="

            # 检查配置文件
            if [ ! -f "$config_file" ]; then
                echo "❌ 配置文件不存在: $config_file"
                continue
            else
                echo "✅ 配置文件存在"
                # 验证JSON格式
                if command -v jq >/dev/null 2>&1; then
                    if ! jq . "$config_file" >/dev/null 2>&1; then
                        echo "❌ 配置文件JSON格式错误"
                        echo "   建议：删除并重新创建此服务"
                        continue
                    else
                        echo "✅ 配置文件格式正确"
                    fi
                else
                    echo "⚠️  无法验证JSON格式 (jq未安装)"
                fi
            fi

            # 检查进程状态
            if [ -f "$pid_file" ]; then
                local pid=$(cat "$pid_file")
                if kill -0 "$pid" 2>/dev/null; then
                    echo "✅ 进程运行中 (PID: $pid)"
                else
                    echo "❌ 进程已停止 (PID文件存在但进程不存在)"
                    rm -f "$pid_file"
                fi
            else
                echo "❌ 进程未运行 (无PID文件)"
            fi

            # 检查日志文件
            if [ -f "$log_file" ]; then
                echo "📋 最近日志 (最后10行):"
                tail -10 "$log_file" | sed 's/^/   /'

                # 检查常见错误
                if grep -q "bind: address already in use" "$log_file"; then
                    echo "⚠️  发现端口冲突错误"
                fi
                if grep -q "connection refused" "$log_file"; then
                    echo "⚠️  发现连接被拒绝错误 (检查上游SOCKS5代理)"
                fi
                if grep -q "permission denied" "$log_file"; then
                    echo "⚠️  发现权限错误"
                fi
            else
                echo "❌ 无日志文件"
            fi

            # 检查端口占用
            if command -v lsof >/dev/null 2>&1; then
                if lsof -i ":$port" >/dev/null 2>&1; then
                    echo "⚠️  端口 $port 被占用:"
                    lsof -i ":$port" | sed 's/^/   /'
                else
                    echo "✅ 端口 $port 未被占用"
                fi
            else
                echo "⚠️  无法检查端口占用 (lsof未安装)"
            fi

            echo ""
        fi
    done

    echo "=== 系统检查 ==="

    # 检查Xray二进制文件
    if [ -f "$XRAY_BIN" ]; then
        echo "✅ Xray二进制文件存在"
        if [ -x "$XRAY_BIN" ]; then
            echo "✅ Xray二进制文件可执行"
            # 测试Xray版本
            if "$XRAY_BIN" version >/dev/null 2>&1; then
                local version=$("$XRAY_BIN" version | head -1)
                echo "✅ Xray版本: $version"
            else
                echo "❌ Xray二进制文件损坏"
                echo "   建议：重新下载Xray"
            fi
        else
            echo "❌ Xray二进制文件无执行权限"
            echo "   修复：chmod +x $XRAY_BIN"
        fi
    else
        echo "❌ Xray二进制文件不存在"
        echo "   建议：重新运行脚本自动下载"
    fi

    # 检查系统资源
    echo ""
    echo "=== 系统资源 ==="
    echo "内存使用:"
    if command -v free >/dev/null 2>&1; then
        free -h
    elif command -v vm_stat >/dev/null 2>&1; then
        vm_stat | head -5
    else
        echo "无法检查内存使用情况"
    fi
    echo ""
    echo "磁盘空间:"
    df -h . | tail -1
}

# 自动修复服务
auto_fix_services() {
    clear
    echo "=== 自动修复服务 ==="
    echo ""

    if [ ! -d "$SERVICE_DIR" ] || [ -z "$(ls -A "$SERVICE_DIR" 2>/dev/null)" ]; then
        echo "暂无服务需要修复"
        return
    fi

    local fixed=0
    local failed=0

    for port_dir in "$SERVICE_DIR"/*; do
        if [ -d "$port_dir" ]; then
            local port=$(basename "$port_dir")
            local status=$(check_status "$port")

            echo "检查端口 $port... 状态: $status"

            if [ "$status" = "已停止" ]; then
                echo "  尝试启动服务..."
                if start_service "$port"; then
                    echo "  ✅ 修复成功"
                    fixed=$((fixed + 1))
                else
                    echo "  ❌ 修复失败"
                    failed=$((failed + 1))
                fi
            else
                echo "  ✅ 服务正常"
            fi
        fi
    done

    echo ""
    echo "修复完成："
    echo "- 成功修复: $fixed 个服务"
    echo "- 修复失败: $failed 个服务"

    if [ $failed -gt 0 ]; then
        echo ""
        echo "建议运行服务诊断查看详细错误信息"
    fi
}

# 启动服务监控
start_monitor() {
    clear
    echo "=== 启动服务监控 ==="
    echo ""

    local monitor_script="$SCRIPT_DIR/monitor.sh"
    local monitor_pid_file="$CONFIG_DIR/monitor.pid"

    # 检查是否已经在运行
    if [ -f "$monitor_pid_file" ]; then
        local monitor_pid=$(cat "$monitor_pid_file")
        if kill -0 "$monitor_pid" 2>/dev/null; then
            echo "服务监控已在运行 (PID: $monitor_pid)"
            echo ""
            echo "监控状态:"
            echo "- 检查间隔: 30秒"
            echo "- 日志文件: $CONFIG_DIR/monitor.log"
            echo ""
            echo "要停止监控，请选择菜单中的 '停止服务监控' 选项"
            return 0
        else
            rm -f "$monitor_pid_file"
        fi
    fi

    # 创建监控脚本
    cat > "$monitor_script" << 'EOF'
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
EOF

    chmod +x "$monitor_script"

    # 启动监控进程
    nohup "$monitor_script" > /dev/null 2>&1 &
    local monitor_pid=$!
    echo "$monitor_pid" > "$monitor_pid_file"

    # 检查监控进程是否启动成功
    sleep 2
    if kill -0 "$monitor_pid" 2>/dev/null; then
        log_success "服务监控启动成功 (PID: $monitor_pid)"
        echo ""
        echo "监控配置:"
        echo "- 检查间隔: 30秒"
        echo "- 自动重启停止的服务"
        echo "- 跳过已过期的服务"
        echo "- 日志文件: $CONFIG_DIR/monitor.log"
        echo ""
        echo "监控进程将在后台持续运行，即使关闭此脚本也会继续工作"
        echo "要停止监控，请选择菜单中的 '停止服务监控' 选项"
    else
        log_error "服务监控启动失败"
        rm -f "$monitor_pid_file"
        return 1
    fi
}

# 停止服务监控
stop_monitor() {
    clear
    echo "=== 停止服务监控 ==="
    echo ""

    local monitor_pid_file="$CONFIG_DIR/monitor.pid"

    if [ ! -f "$monitor_pid_file" ]; then
        echo "服务监控未运行"
        return 0
    fi

    local monitor_pid=$(cat "$monitor_pid_file")
    if kill -0 "$monitor_pid" 2>/dev/null; then
        echo "正在停止服务监控 (PID: $monitor_pid)..."
        kill -TERM "$monitor_pid" 2>/dev/null || true

        # 等待进程退出
        for i in {1..10}; do
            if ! kill -0 "$monitor_pid" 2>/dev/null; then
                break
            fi
            sleep 0.5
        done

        # 如果还没退出，强制终止
        if kill -0 "$monitor_pid" 2>/dev/null; then
            kill -KILL "$monitor_pid" 2>/dev/null || true
        fi

        log_success "服务监控已停止"
    else
        echo "监控进程不存在"
    fi

    rm -f "$monitor_pid_file"
}

# 查看监控日志
view_monitor_log() {
    clear
    echo "=== 监控日志 ==="
    echo ""

    local monitor_log="$CONFIG_DIR/monitor.log"

    if [ ! -f "$monitor_log" ]; then
        echo "监控日志文件不存在"
        echo "可能原因："
        echo "1. 服务监控从未启动过"
        echo "2. 日志文件被删除"
        return 0
    fi

    echo "最近50行监控日志："
    echo "----------------------------------------"
    tail -50 "$monitor_log"
    echo "----------------------------------------"
    echo ""
    echo "日志文件位置: $monitor_log"
    echo "日志文件大小: $(du -h "$monitor_log" | cut -f1)"
}

# 主菜单
main_menu() {
    while true; do
        clear
        echo "=================================="
        echo "  Xray SOCKS5 -> SS 转换器"
        echo "      (超简化版本)"
        echo "=================================="
        echo ""
        echo "1. 添加服务"
        echo "2. 列出服务"
        echo "3. 查看服务详情"
        echo "4. 编辑服务"
        echo "5. 续费服务"
        echo "6. 删除服务"
        echo "7. 重启所有服务"
        echo "8. 启动服务监控"
        echo "9. 停止服务监控"
        echo "10. 查看监控日志"
        echo "11. 备份配置"
        echo "12. 恢复配置"
        echo "13. 管理备份"
        echo "14. 服务诊断"
        echo "15. 自动修复"
        echo "0. 退出"
        echo ""
        read -p "请选择 [0-15]: " choice

        case $choice in
            1) add_service; read -p "按回车继续..." ;;
            2) list_services; read -p "按回车继续..." ;;
            3) view_service; read -p "按回车继续..." ;;
            4) edit_service; read -p "按回车继续..." ;;
            5) renew_service; read -p "按回车继续..." ;;
            6) delete_service; read -p "按回车继续..." ;;
            7) restart_all; read -p "按回车继续..." ;;
            8) start_monitor; read -p "按回车继续..." ;;
            9) stop_monitor; read -p "按回车继续..." ;;
            10) view_monitor_log; read -p "按回车继续..." ;;
            11) backup_config; read -p "按回车继续..." ;;
            12) restore_config; read -p "按回车继续..." ;;
            13) manage_backups; read -p "按回车继续..." ;;
            14) diagnose_service; read -p "按回车继续..." ;;
            15) auto_fix_services; read -p "按回车继续..." ;;
            0) echo "再见！"; exit 0 ;;
            *) echo "无效选择" ;;
        esac
    done
}

# 启动单个服务 (供监控脚本调用)
start_single_service() {
    local port="$1"
    if [ -z "$port" ]; then
        echo "错误: 未指定端口"
        return 1
    fi

    if [ ! -d "$SERVICE_DIR/$port" ]; then
        echo "错误: 服务不存在"
        return 1
    fi

    start_service "$port"
}

# 停止单个服务 (供Web API调用)
stop_single_service() {
    local port="$1"
    if [ -z "$port" ]; then
        echo "错误: 未指定端口"
        return 1
    fi

    if [ ! -d "$SERVICE_DIR/$port" ]; then
        echo "错误: 服务不存在"
        return 1
    fi

    stop_service "$port"
}

# 删除服务 (供Web API调用)
delete_service_api() {
    local port="$1"
    if [ -z "$port" ]; then
        echo "错误: 未指定端口"
        return 1
    fi

    if [ ! -d "$SERVICE_DIR/$port" ]; then
        echo "错误: 服务不存在"
        return 1
    fi

    # 先停止服务
    stop_service "$port" 2>/dev/null || true

    # 删除服务目录
    rm -rf "$SERVICE_DIR/$port"

    log_success "服务已删除: 端口 $port"
    return 0
}

# 重启所有服务
restart_all() {
    clear
    echo "=== 重启所有服务 ==="
    echo ""

    local count=0
    for port_dir in "$SERVICE_DIR"/*; do
        if [ -d "$port_dir" ]; then
            local port=$(basename "$port_dir")
            echo "重启端口 $port..."
            stop_service "$port"
            sleep 1
            start_service "$port"
            count=$((count + 1))
        fi
    done

    log_success "已重启 $count 个服务"
}

# 系统优化
optimize_system() {
    log "正在优化系统参数..."

    # 检查并设置文件描述符限制
    local current_limit=$(ulimit -n)
    if [ "$current_limit" -lt 65536 ]; then
        log "当前文件描述符限制: $current_limit，建议增加到65536"

        # 尝试临时增加限制
        if ulimit -n 65536 2>/dev/null; then
            log "已临时增加文件描述符限制到65536"
        else
            log "无法增加文件描述符限制，可能需要root权限"
            echo "建议在 /etc/security/limits.conf 中添加："
            echo "* soft nofile 65536"
            echo "* hard nofile 65536"
        fi
    fi

    # 检查系统内核参数
    if [ -w /proc/sys/net/core/somaxconn ]; then
        echo 65536 > /proc/sys/net/core/somaxconn 2>/dev/null || true
    fi

    if [ -w /proc/sys/net/core/netdev_max_backlog ]; then
        echo 5000 > /proc/sys/net/core/netdev_max_backlog 2>/dev/null || true
    fi

    if [ -w /proc/sys/net/ipv4/tcp_max_syn_backlog ]; then
        echo 65536 > /proc/sys/net/ipv4/tcp_max_syn_backlog 2>/dev/null || true
    fi

    # 检查是否有足够的内存
    local mem_total_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    local mem_total_mb=$((mem_total_kb / 1024))

    if [ $mem_total_mb -lt 512 ]; then
        log "警告: 系统内存较少 (${mem_total_mb}MB)，建议至少512MB"
    fi

    log "系统优化完成"
}

# 初始化
init() {
    mkdir -p "$CONFIG_DIR" "$SERVICE_DIR"

    if ! ensure_xray; then
        log_error "Xray初始化失败"
        exit 1
    fi

    # 执行系统优化
    optimize_system

    log_success "初始化完成"
}

# 简化初始化 (用于Web API)
init_simple() {
    mkdir -p "$CONFIG_DIR" "$SERVICE_DIR"
    log_success "简化初始化完成"
}

# 主程序
main() {
    # 检查是否有命令行参数
    if [ $# -gt 0 ]; then
        # Web API调用，使用简化初始化
        init_simple

        case "$1" in
            "add_service")
                if [ $# -ge 4 ]; then
                    add_service_api "$2" "$3" "$4"
                else
                    echo "错误: 参数不足 (需要: 端口 密码 节点名称)"
                    exit 1
                fi
                ;;
            "start_single_service")
                if [ $# -ge 2 ]; then
                    start_single_service "$2"
                else
                    echo "错误: 缺少端口参数"
                    exit 1
                fi
                ;;
            "stop_single_service")
                if [ $# -ge 2 ]; then
                    stop_single_service "$2"
                else
                    echo "错误: 缺少端口参数"
                    exit 1
                fi
                ;;
            "delete_service_api")
                if [ $# -ge 2 ]; then
                    delete_service_api "$2"
                else
                    echo "错误: 缺少端口参数"
                    exit 1
                fi
                ;;
            *)
                echo "未知命令: $1"
                exit 1
                ;;
        esac
    else
        # 交互式调用，使用完整初始化
        init
        main_menu
    fi
}

# 启动
main "$@"
