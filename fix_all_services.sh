#!/bin/bash

echo "🔧 服务修复脚本"
echo "================"

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then
    echo "请以root用户运行此脚本"
    exit 1
fi

# 停止所有xray进程
echo "🛑 停止所有xray进程..."
pkill -f xray || true
sleep 2

# 强制杀死残留进程
echo "🔥 清理残留进程..."
pkill -9 -f xray || true
sleep 1

# 清理PID文件
echo "🧹 清理PID文件..."
find data/services/ -name "*.pid" -delete 2>/dev/null || true

# 检查并修复xray二进制文件
echo "🔍 检查xray二进制文件..."
if [ ! -f "xray" ] || ! ./xray version >/dev/null 2>&1; then
    echo "🔧 修复xray二进制文件..."
    ./fix_xray.sh
fi

# 重新启动所有服务
echo "🚀 重新启动所有服务..."
if [ -d "data/services" ]; then
    for service_dir in data/services/*/; do
        if [ -d "$service_dir" ]; then
            port=$(basename "$service_dir")
            echo "启动服务: $port"
            
            # 检查配置文件
            if [ -f "$service_dir/config.json" ]; then
                # 使用脚本启动服务
                bash xray_converter_simple.sh start_single_service "$port" || echo "启动失败: $port"
            else
                echo "❌ 配置文件不存在: $service_dir/config.json"
            fi
        fi
    done
else
    echo "❌ 服务目录不存在"
fi

echo ""
echo "🔍 检查启动结果..."
sleep 3

# 检查进程状态
echo "当前xray进程:"
ps aux | grep xray | grep -v grep || echo "没有xray进程在运行"

echo ""
echo "端口占用情况:"
netstat -tlnp | grep xray || echo "没有xray占用的端口"

echo ""
echo "✅ 服务修复完成"
echo ""
echo "💡 如果问题仍然存在，请检查:"
echo "1. 系统资源是否充足 (CPU < 80%, 内存 > 100MB)"
echo "2. SOCKS5后端代理是否可用"
echo "3. 防火墙是否阻止了端口"
echo "4. 服务器是否需要重启"