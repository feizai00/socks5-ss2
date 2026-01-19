#!/bin/bash
# Xray SOCKS5转SS 简洁命令行管理工具

DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICES="$DIR/data/services"
XRAY="$DIR/xray"

help() {
    echo "Xray SOCKS5转SS 管理工具"
    echo ""
    echo "用法: $0 <命令> [参数]"
    echo ""
    echo "命令:"
    echo "  ls                  - 列出所有服务"
    echo "  add IP:PORT [名称]  - 添加服务"
    echo "  start PORT          - 启动服务"
    echo "  stop PORT           - 停止服务"
    echo "  del PORT            - 删除服务"
    echo "  info PORT           - 服务信息"
    echo ""
    echo "示例:"
    echo "  $0 ls"
    echo "  $0 add 192.168.1.100:1080 美国节点"
    echo "  $0 start 8080"
}

ls_cmd() {
    echo "端口    状态      节点名"
    echo "------------------------"
    
    if [ ! -d "$SERVICES" ]; then
        echo "无服务"
        return
    fi
    
    for d in "$SERVICES"/*; do
        if [ -d "$d" ]; then
            port=$(basename "$d")
            name=$(grep '^NODE_NAME=' "$d/info" 2>/dev/null | cut -d= -f2 || echo "未知")
            
            if [ -f "$d/xray.pid" ] && kill -0 $(cat "$d/xray.pid" 2>/dev/null) 2>/dev/null; then
                status="运行中"
            else
                status="已停止"
            fi
            
            printf "%-8s %-10s %s\n" "$port" "$status" "$name"
        fi
    done
}

add_cmd() {
    if [ $# -lt 1 ]; then
        echo "用法: $0 add IP:PORT [名称]"
        return 1
    fi
    
    backend="$1"
    name="${2:-节点_$(date +%m%d)}"
    
    if [[ ! "$backend" =~ ^[0-9.]+:[0-9]+$ ]]; then
        echo "格式错误，应为: IP:端口"
        return 1
    fi
    
    ip=$(echo "$backend" | cut -d: -f1)
    socks_port=$(echo "$backend" | cut -d: -f2)
    
    # 生成随机端口和密码
    ss_port=$(($RANDOM + 10000))
    while netstat -ln 2>/dev/null | grep -q ":$ss_port "; do
        ss_port=$(($RANDOM + 10000))
    done
    
    password=$(tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 12)
    
    # 创建服务目录
    mkdir -p "$SERVICES/$ss_port"
    
    # 创建信息文件
    cat > "$SERVICES/$ss_port/info" << EOF
NODE_NAME=$name
PASSWORD=$password
SOCKS_IP=$ip
SOCKS_PORT=$socks_port
CREATED=$(date)
STATUS=stopped
EOF

    # 创建Xray配置
    cat > "$SERVICES/$ss_port/config.json" << EOF
{
    "inbounds": [{
        "port": $ss_port,
        "protocol": "shadowsocks",
        "settings": {
            "method": "chacha20-ietf-poly1305",
            "password": "$password"
        }
    }],
    "outbounds": [{
        "protocol": "socks",
        "settings": {
            "servers": [{
                "address": "$ip",
                "port": $socks_port
            }]
        }
    }]
}
EOF

    echo "服务创建成功!"
    echo "SS端口: $ss_port"
    echo "SS密码: $password"
    echo "节点名: $name"
    echo "后端: $backend"
    
    # 生成SS链接
    server_ip=$(curl -s ifconfig.me 2>/dev/null || echo "YOUR_SERVER_IP")
    ss_link="ss://$(echo -n "chacha20-ietf-poly1305:$password" | base64)@$server_ip:$ss_port#$name"
    echo "SS链接: $ss_link"
}

start_cmd() {
    if [ $# -lt 1 ]; then
        echo "用法: $0 start PORT"
        return 1
    fi
    
    port="$1"
    service_dir="$SERVICES/$port"
    
    if [ ! -d "$service_dir" ]; then
        echo "服务 $port 不存在"
        return 1
    fi
    
    # 检查是否已运行
    if [ -f "$service_dir/xray.pid" ] && kill -0 $(cat "$service_dir/xray.pid" 2>/dev/null) 2>/dev/null; then
        echo "服务 $port 已在运行"
        return 0
    fi
    
    # 启动服务
    cd "$service_dir"
    nohup "$XRAY" -c config.json > xray.log 2>&1 &
    echo $! > xray.pid
    
    sleep 1
    
    if kill -0 $(cat xray.pid 2>/dev/null) 2>/dev/null; then
        echo "服务 $port 启动成功"
        sed -i 's/STATUS=.*/STATUS=running/' info 2>/dev/null
    else
        echo "服务 $port 启动失败"
        rm -f xray.pid
        return 1
    fi
}

stop_cmd() {
    if [ $# -lt 1 ]; then
        echo "用法: $0 stop PORT"
        return 1
    fi
    
    port="$1"
    service_dir="$SERVICES/$port"
    
    if [ ! -d "$service_dir" ]; then
        echo "服务 $port 不存在"
        return 1
    fi
    
    if [ -f "$service_dir/xray.pid" ]; then
        pid=$(cat "$service_dir/xray.pid" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            sleep 1
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$service_dir/xray.pid"
        sed -i 's/STATUS=.*/STATUS=stopped/' "$service_dir/info" 2>/dev/null
        echo "服务 $port 已停止"
    else
        echo "服务 $port 未运行"
    fi
}

del_cmd() {
    if [ $# -lt 1 ]; then
        echo "用法: $0 del PORT"
        return 1
    fi
    
    port="$1"
    service_dir="$SERVICES/$port"
    
    if [ ! -d "$service_dir" ]; then
        echo "服务 $port 不存在"
        return 1
    fi
    
    # 先停止服务
    stop_cmd "$port"
    
    # 删除目录
    rm -rf "$service_dir"
    echo "服务 $port 已删除"
}

info_cmd() {
    if [ $# -lt 1 ]; then
        echo "用法: $0 info PORT"
        return 1
    fi
    
    port="$1"
    service_dir="$SERVICES/$port"
    
    if [ ! -d "$service_dir" ]; then
        echo "服务 $port 不存在"
        return 1
    fi
    
    echo "服务 $port 信息:"
    echo "----------------"
    if [ -f "$service_dir/info" ]; then
        cat "$service_dir/info"
    fi
    
    echo "----------------"
    if [ -f "$service_dir/xray.pid" ] && kill -0 $(cat "$service_dir/xray.pid" 2>/dev/null) 2>/dev/null; then
        echo "状态: 运行中 (PID: $(cat "$service_dir/xray.pid"))"
    else
        echo "状态: 已停止"
    fi
}

# 主程序
case "${1:-help}" in
    ls|list) ls_cmd ;;
    add) shift; add_cmd "$@" ;;
    start) shift; start_cmd "$@" ;;
    stop) shift; stop_cmd "$@" ;;
    del|delete|rm) shift; del_cmd "$@" ;;
    info|status) shift; info_cmd "$@" ;;
    help|--help|-h|*) help ;;
esac