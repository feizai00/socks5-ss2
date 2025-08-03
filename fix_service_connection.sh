#!/bin/bash

echo "🔧 服务连接问题专项修复"
echo "========================"

if [ $# -eq 0 ]; then
    echo "用法: $0 <端口号> [检查模式]"
    echo "示例: $0 29657"
    echo "检查模式: $0 29657 check"
    exit 1
fi

PORT=$1
CHECK_MODE=${2:-""}
SERVICE_DIR="data/services/$PORT"

echo "🎯 修复端口: $PORT"
echo "📁 服务目录: $SERVICE_DIR"

# 检查服务目录
if [ ! -d "$SERVICE_DIR" ]; then
    echo "❌ 服务目录不存在: $SERVICE_DIR"
    exit 1
fi

echo ""
echo "🔍 第一步: 检查配置文件"
echo "======================"

# 检查配置文件
CONFIG_FILE="$SERVICE_DIR/config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ 配置文件不存在: $CONFIG_FILE"
    exit 1
fi

echo "✅ 配置文件存在"
echo "📄 配置内容:"
cat "$CONFIG_FILE" | python3 -m json.tool 2>/dev/null || {
    echo "❌ JSON格式错误，正在修复..."
    
    # 从环境文件重新生成配置
    if [ -f "$SERVICE_DIR/config.env" ]; then
        source "$SERVICE_DIR/config.env"
        
        # 生成新的配置文件
        cat > "$CONFIG_FILE" << EOF
{
  "log": {
    "loglevel": "warning"
  },
  "inbounds": [
    {
      "port": $PORT,
      "protocol": "shadowsocks",
      "settings": {
        "method": "chacha20-ietf-poly1305",
        "password": "$PASSWORD"
      }
    }
  ],
  "outbounds": [
    {
      "protocol": "socks",
      "settings": {
        "servers": [
          {
            "address": "$SOCKS_IP",
            "port": $SOCKS_PORT$(if [ -n "$SOCKS_USER" ] && [ -n "$SOCKS_PASS" ]; then echo ",
            \"users\": [
              {
                \"user\": \"$SOCKS_USER\",
                \"pass\": \"$SOCKS_PASS\"
              }
            ]"; fi)
          }
        ]
      }
    }
  ]
}
EOF
        echo "✅ 配置文件已重新生成"
    else
        echo "❌ 环境文件也不存在，无法修复"
        exit 1
    fi
}

echo ""
echo "🔍 第二步: 测试SOCKS5后端"
echo "======================"

# 从配置文件提取SOCKS5信息
if [ -f "$SERVICE_DIR/config.env" ]; then
    source "$SERVICE_DIR/config.env"
    echo "SOCKS5后端: $SOCKS_IP:$SOCKS_PORT"
    
    # 测试SOCKS5连接
    echo "测试SOCKS5连接..."
    if timeout 5 bash -c "</dev/tcp/$SOCKS_IP/$SOCKS_PORT" 2>/dev/null; then
        echo "✅ SOCKS5后端连接成功"
    else
        echo "❌ SOCKS5后端连接失败"
        echo "🔧 可能的解决方案:"
        echo "1. 检查SOCKS5代理是否在线"
        echo "2. 检查防火墙设置"
        echo "3. 检查网络连接"
        
        if [ "$CHECK_MODE" != "check" ]; then
            echo "是否继续修复? (y/n)"
            read -r answer
            if [ "$answer" != "y" ]; then
                exit 1
            fi
        fi
    fi
else
    echo "❌ 无法获取SOCKS5信息"
    exit 1
fi

if [ "$CHECK_MODE" = "check" ]; then
    echo "✅ 检查模式完成"
    exit 0
fi

echo ""
echo "🔍 第三步: 停止现有服务"
echo "======================"

# 停止现有服务
PID_FILE="$SERVICE_DIR/xray.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "停止现有服务 (PID: $PID)..."
        kill -TERM "$PID" 2>/dev/null || true
        sleep 2
        if kill -0 "$PID" 2>/dev/null; then
            kill -KILL "$PID" 2>/dev/null || true
        fi
    fi
    rm -f "$PID_FILE"
fi

# 确保端口释放
echo "检查端口占用..."
if netstat -tlnp 2>/dev/null | grep ":$PORT " >/dev/null; then
    echo "端口仍被占用，强制清理..."
    fuser -k $PORT/tcp 2>/dev/null || true
    sleep 1
fi

echo ""
echo "🔍 第四步: 验证Xray二进制"
echo "======================"

if [ ! -f "xray" ] || [ ! -x "xray" ]; then
    echo "❌ xray二进制文件问题，正在修复..."
    ./fix_xray.sh || {
        echo "❌ xray修复失败"
        exit 1
    }
fi

# 测试配置文件
echo "验证配置文件..."
if ! ./xray run -test -config "$CONFIG_FILE" 2>/dev/null; then
    echo "❌ 配置文件验证失败"
    echo "配置文件内容:"
    cat "$CONFIG_FILE"
    exit 1
fi

echo "✅ 配置文件验证通过"

echo ""
echo "🔍 第五步: 启动服务"
echo "=================="

# 启动服务
LOG_FILE="$SERVICE_DIR/xray.log"
echo "启动服务..."

# 清理旧日志
> "$LOG_FILE"

# 启动xray
nohup ./xray run -config "$CONFIG_FILE" > "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

echo "服务已启动 (PID: $NEW_PID)"

# 等待服务稳定
echo "等待服务稳定..."
sleep 3

# 检查进程状态
if ! kill -0 "$NEW_PID" 2>/dev/null; then
    echo "❌ 服务启动失败"
    echo "日志内容:"
    cat "$LOG_FILE"
    exit 1
fi

echo "✅ 服务运行正常"

echo ""
echo "🔍 第六步: 验证端口监听"
echo "======================"

# 检查端口监听
sleep 2
if netstat -tlnp 2>/dev/null | grep ":$PORT " >/dev/null; then
    echo "✅ 端口 $PORT 正在监听"
    netstat -tlnp | grep ":$PORT "
else
    echo "❌ 端口 $PORT 未监听"
    echo "检查日志:"
    tail -20 "$LOG_FILE"
    exit 1
fi

echo ""
echo "🔍 第七步: 测试SS连接"
echo "==================="

# 生成SS链接进行测试
if [ -f "$SERVICE_DIR/config.env" ]; then
    source "$SERVICE_DIR/config.env"
    
    # 获取服务器IP
    SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s ipinfo.io/ip 2>/dev/null || echo "127.0.0.1")
    
    # 生成SS链接
    AUTH_STRING="chacha20-ietf-poly1305:$PASSWORD"
    AUTH_ENCODED=$(echo -n "$AUTH_STRING" | base64 -w 0 2>/dev/null || echo -n "$AUTH_STRING" | base64)
    SS_LINK="ss://${AUTH_ENCODED}@${SERVER_IP}:${PORT}/#${NODE_NAME:-test}"
    
    echo "SS链接: $SS_LINK"
    
    # 使用内置测试工具测试
    if [ -f "test_ss_link.py" ]; then
        echo "测试SS链接连接性..."
        python3 test_ss_link.py "$SS_LINK" || echo "SS链接测试失败，但服务可能正常运行"
    fi
fi

echo ""
echo "✅ 服务修复完成!"
echo "===================="
echo "端口: $PORT"
echo "状态: 运行中"
echo "PID: $NEW_PID"
echo "配置: $CONFIG_FILE"
echo "日志: $LOG_FILE"

if [ -n "$SS_LINK" ]; then
    echo "SS链接: $SS_LINK"
fi

echo ""
echo "💡 如果仍然无法连接，请检查:"
echo "1. 客户端配置是否正确"
echo "2. 服务器防火墙是否开放端口 $PORT"
echo "3. SOCKS5后端代理是否稳定"