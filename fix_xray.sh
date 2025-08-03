#!/bin/bash

echo "🔧 Xray自动修复脚本"
echo "=================="

# 检测系统架构
ARCH=$(uname -m)
echo "🖥️  检测到系统架构: $ARCH"

# 根据架构选择下载链接
if [[ "$ARCH" == "x86_64" ]]; then
    DOWNLOAD_URL="https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip"
    echo "📥 将下载 Linux x64 版本"
elif [[ "$ARCH" == "aarch64" ]] || [[ "$ARCH" == "arm64" ]]; then
    DOWNLOAD_URL="https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-arm64-v8a.zip"
    echo "📥 将下载 Linux ARM64 版本"
else
    echo "❌ 不支持的架构: $ARCH"
    echo "请手动下载适合的版本"
    exit 1
fi

# 备份旧文件
if [ -f "xray" ]; then
    echo "💾 备份旧的xray文件"
    mv xray xray.backup.$(date +%Y%m%d_%H%M%S)
fi

# 下载新的xray
echo "📥 下载最新的Xray..."
if command -v wget >/dev/null 2>&1; then
    wget -O xray.zip "$DOWNLOAD_URL"
elif command -v curl >/dev/null 2>&1; then
    curl -L -o xray.zip "$DOWNLOAD_URL"
else
    echo "❌ 需要wget或curl来下载文件"
    exit 1
fi

# 检查下载是否成功
if [ ! -f "xray.zip" ]; then
    echo "❌ 下载失败"
    exit 1
fi

# 解压
echo "📦 解压xray..."
if command -v unzip >/dev/null 2>&1; then
    unzip -o xray.zip
else
    echo "❌ 需要unzip来解压文件"
    exit 1
fi

# 设置权限
echo "🔐 设置执行权限..."
chmod +x xray

# 清理
echo "🧹 清理临时文件..."
rm -f xray.zip

# 验证
echo "✅ 验证新的xray..."
if [ -f "xray" ] && [ -x "xray" ]; then
    echo "🔍 测试xray版本:"
    timeout 10 ./xray version 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ Xray修复成功！"
    else
        echo "⚠️  Xray可能仍有问题，但文件已更新"
    fi
else
    echo "❌ 修复失败"
    exit 1
fi

echo ""
echo "🎉 修复完成！现在可以尝试启动服务了。"