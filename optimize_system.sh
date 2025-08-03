#!/bin/bash

echo "⚡ 系统优化脚本"
echo "================"

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then
    echo "请以root用户运行此脚本"
    exit 1
fi

# 清理系统缓存
echo "🧹 清理系统缓存..."
sync
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
echo "✅ 缓存清理完成"

# 优化内存设置
echo "🔧 优化内存设置..."
echo "vm.swappiness=10" >> /etc/sysctl.conf 2>/dev/null || true
echo "vm.vfs_cache_pressure=50" >> /etc/sysctl.conf 2>/dev/null || true
sysctl -p >/dev/null 2>&1 || true
echo "✅ 内存优化完成"

# 限制日志文件大小
echo "📝 限制日志文件大小..."
if [ -d "data/services" ]; then
    find data/services/ -name "*.log" -size +10M -exec truncate -s 1M {} \; 2>/dev/null || true
    echo "✅ 日志文件已清理"
fi

# 清理临时文件
echo "🗑️ 清理临时文件..."
rm -rf /tmp/xray* 2>/dev/null || true
rm -rf data/services/.recycle/* 2>/dev/null || true
echo "✅ 临时文件清理完成"

# 优化进程限制
echo "🔧 优化进程限制..."
ulimit -n 65535 2>/dev/null || true
echo "* soft nofile 65535" >> /etc/security/limits.conf 2>/dev/null || true
echo "* hard nofile 65535" >> /etc/security/limits.conf 2>/dev/null || true
echo "✅ 进程限制优化完成"

# 检查并杀死占用CPU的进程
echo "🔍 检查高CPU使用进程..."
HIGH_CPU_PIDS=$(ps aux --sort=-%cpu | awk 'NR>1 && $3>50 {print $2}' | head -5)
if [ -n "$HIGH_CPU_PIDS" ]; then
    echo "发现高CPU使用进程，正在处理..."
    for pid in $HIGH_CPU_PIDS; do
        PROCESS_NAME=$(ps -p $pid -o comm= 2>/dev/null || echo "unknown")
        if [[ "$PROCESS_NAME" != "xray" ]] && [[ "$PROCESS_NAME" != "python3" ]]; then
            echo "终止高CPU进程: $pid ($PROCESS_NAME)"
            kill -TERM $pid 2>/dev/null || true
        fi
    done
fi

# 重启网络服务
echo "🌐 重启网络服务..."
systemctl restart networking 2>/dev/null || service networking restart 2>/dev/null || true

# 显示优化后的系统状态
echo ""
echo "📊 优化后系统状态:"
echo "内存使用:"
free -h | grep Mem
echo "CPU负载:"
uptime
echo "磁盘使用:"
df -h / | tail -1

echo ""
echo "✅ 系统优化完成"
echo ""
echo "💡 建议接下来执行:"
echo "1. ./fix_all_services.sh  # 修复所有服务"
echo "2. 重启服务器 (如果问题仍然存在)"