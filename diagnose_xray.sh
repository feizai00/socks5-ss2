#!/bin/bash

echo "🔍 Xray诊断和修复脚本"
echo "===================="

# 检查当前目录
echo "📁 当前目录: $(pwd)"

# 检查xray文件
echo ""
echo "📋 检查xray文件:"
if [ -f "xray" ]; then
    echo "✅ xray文件存在"
    echo "📊 文件信息:"
    ls -la xray
    echo ""
    echo "🔍 文件类型:"
    file xray
    echo ""
    echo "🔍 文件头部内容:"
    head -c 100 xray | xxd
else
    echo "❌ xray文件不存在"
fi

# 检查系统架构
echo ""
echo "🖥️  系统信息:"
echo "架构: $(uname -m)"
echo "系统: $(uname -s)"
echo "内核: $(uname -r)"

# 检查是否有其他xray进程
echo ""
echo "🔍 检查xray进程:"
ps aux | grep xray | grep -v grep || echo "没有运行的xray进程"

# 检查权限
echo ""
echo "🔐 检查执行权限:"
if [ -x "xray" ]; then
    echo "✅ xray有执行权限"
else
    echo "❌ xray没有执行权限"
    echo "🔧 正在添加执行权限..."
    chmod +x xray
fi

# 尝试获取xray版本
echo ""
echo "🔍 测试xray可执行性:"
if [ -f "xray" ]; then
    echo "尝试运行: ./xray version"
    timeout 5 ./xray version 2>&1 || echo "❌ xray无法正常执行"
fi

# 提供修复建议
echo ""
echo "🛠️  修复建议:"
echo "如果xray文件损坏，请运行以下命令重新下载:"
echo ""
echo "# 下载适合Linux x64的xray"
echo "wget -O xray.zip https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip"
echo "unzip -o xray.zip"
echo "chmod +x xray"
echo "rm xray.zip"
echo ""
echo "# 或者下载适合ARM64的xray"
echo "wget -O xray.zip https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-arm64-v8a.zip"
echo "unzip -o xray.zip"
echo "chmod +x xray"
echo "rm xray.zip"

echo ""
echo "✅ 诊断完成"