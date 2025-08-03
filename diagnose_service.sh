#!/bin/bash

echo "🔍 服务诊断脚本"
echo "================"

if [ $# -eq 0 ]; then
    echo "用法: $0 <端口号>"
    echo "示例: $0 29657"
    exit 1
fi

PORT=$1
SERVICE_DIR="data/services/$PORT"

echo "📋 诊断端口: $PORT"
echo "📁 服务目录: $SERVICE_DIR"

# 检查服务目录
if [ ! -d "$SERVICE_DIR" ]; then
    echo "❌ 服务目录不存在: $SERVICE_DIR"
    exit 1
fi

echo "✅ 服务目录存在"

# 检查文件
echo ""
echo "📄 检查服务文件:"
for file in config.json config.env info.txt; do
    if [ -f "$SERVICE_DIR/$file" ]; then
        echo "✅ $file 存在"
    else
        echo "❌ $file 不存在"
    fi
done

# 检查配置文件内容
if [ -f "$SERVICE_DIR/config.json" ]; then
    echo ""
    echo "🔍 Xray配置文件内容:"
    echo "===================="
    cat "$SERVICE_DIR/config.json" | python3 -m json.tool 2>/dev/null || cat "$SERVICE_DIR/config.json"
fi

if [ -f "$SERVICE_DIR/config.env" ]; then
    echo ""
    echo "🔍 环境配置文件内容:"
    echo "===================="
    cat "$SERVICE_DIR/config.env"
fi

# 检查进程状态
echo ""
echo "🔍 进程状态:"
PID_FILE="$SERVICE_DIR/xray.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    echo "📄 PID文件存在: $PID"
    if kill -0 "$PID" 2>/dev/null; then
        echo "✅ 进程正在运行 (PID: $PID)"
        echo "📊 进程信息:"
        ps aux | grep "$PID" | grep -v grep
    else
        echo "❌ 进程未运行 (PID文件存在但进程不存在)"
    fi
else
    echo "📄 PID文件不存在"
fi

# 检查端口占用
echo ""
echo "🔍 端口占用状态:"
if command -v netstat >/dev/null 2>&1; then
    netstat -tlnp | grep ":$PORT " || echo "端口 $PORT 未被占用"
elif command -v ss >/dev/null 2>&1; then
    ss -tlnp | grep ":$PORT " || echo "端口 $PORT 未被占用"
else
    echo "无法检查端口占用状态 (缺少netstat或ss命令)"
fi

# 检查日志文件
echo ""
echo "🔍 日志文件:"
LOG_FILE="$SERVICE_DIR/xray.log"
if [ -f "$LOG_FILE" ]; then
    echo "📄 日志文件存在，最近10行:"
    echo "=========================="
    tail -10 "$LOG_FILE"
else
    echo "📄 日志文件不存在"
fi

# 测试配置文件语法
echo ""
echo "🔍 测试Xray配置:"
if [ -f "xray" ] && [ -x "xray" ]; then
    echo "正在验证配置文件语法..."
    ./xray run -test -config "$SERVICE_DIR/config.json" 2>&1
else
    echo "❌ xray二进制文件不存在或无执行权限"
fi

# 检查SOCKS5后端连接
if [ -f "$SERVICE_DIR/config.env" ]; then
    echo ""
    echo "🔍 测试SOCKS5后端连接:"
    SOCKS_IP=$(grep "SOCKS_IP=" "$SERVICE_DIR/config.env" | cut -d'=' -f2)
    SOCKS_PORT=$(grep "SOCKS_PORT=" "$SERVICE_DIR/config.env" | cut -d'=' -f2)
    
    if [ -n "$SOCKS_IP" ] && [ -n "$SOCKS_PORT" ]; then
        echo "测试连接到 $SOCKS_IP:$SOCKS_PORT ..."
        if timeout 5 bash -c "</dev/tcp/$SOCKS_IP/$SOCKS_PORT" 2>/dev/null; then
            echo "✅ SOCKS5后端连接成功"
        else
            echo "❌ SOCKS5后端连接失败"
        fi
    else
        echo "❌ 无法获取SOCKS5后端信息"
    fi
fi

echo ""
echo "✅ 诊断完成"