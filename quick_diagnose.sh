#!/bin/bash

echo "🚨 快速诊断脚本"
echo "================"

# 检查系统资源
echo "📊 系统资源状态:"
echo "CPU使用率:"
top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//'
echo "内存使用:"
free -h | grep Mem
echo "磁盘使用:"
df -h / | tail -1

echo ""
echo "🔍 检查Xray进程:"
ps aux | grep xray | grep -v grep || echo "没有找到xray进程"

echo ""
echo "🔍 检查端口占用:"
echo "检查常见端口..."
for port in 29657 48677 46542; do
    if netstat -tlnp 2>/dev/null | grep ":$port " >/dev/null; then
        echo "✅ 端口 $port 被占用"
        netstat -tlnp | grep ":$port "
    else
        echo "❌ 端口 $port 未被占用"
    fi
done

echo ""
echo "🔍 检查服务目录:"
if [ -d "data/services" ]; then
    echo "服务目录存在，服务数量: $(ls data/services/ | wc -l)"
    echo "最近创建的服务:"
    ls -lt data/services/ | head -5
else
    echo "❌ 服务目录不存在"
fi

echo ""
echo "🔍 检查Xray二进制文件:"
if [ -f "xray" ]; then
    echo "✅ xray文件存在"
    ls -la xray
    echo "测试xray版本:"
    timeout 5 ./xray version 2>&1 || echo "❌ xray无法执行"
else
    echo "❌ xray文件不存在"
fi

echo ""
echo "🔍 检查最近的错误日志:"
echo "查找最近的错误..."
if [ -d "data/services" ]; then
    find data/services/ -name "*.log" -type f -exec tail -5 {} \; 2>/dev/null | grep -i error | head -10
fi

echo ""
echo "💡 建议操作:"
echo "1. 如果CPU使用率过高，重启服务器"
echo "2. 如果xray无法执行，运行: ./fix_xray.sh"
echo "3. 如果端口未占用但服务显示运行中，重启所有服务"
echo "4. 检查磁盘空间是否充足"

echo ""
echo "✅ 快速诊断完成"