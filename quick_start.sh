#!/bin/bash
# 快速启动脚本 - 服务器部署后的快速验证工具

set -euo pipefail

echo "========================================"
echo "  Xray转换器 - 快速启动检查"
echo "========================================"
echo ""

# 检查是否在正确目录
if [ ! -f "xray_converter_simple.sh" ]; then
    echo "❌ 请在项目根目录运行此脚本"
    exit 1
fi

echo "✅ 项目目录检查通过"

# 设置权限
echo "🔧 设置文件权限..."
chmod +x *.sh *.py 2>/dev/null || true
echo "✅ 权限设置完成"

# 检查系统环境
echo "🖥️  检查系统环境..."
echo "操作系统: $(uname -s) $(uname -m)"

# 检查依赖
missing_deps=()
for cmd in curl wget unzip; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        missing_deps+=("$cmd")
    fi
done

if [ ${#missing_deps[@]} -gt 0 ]; then
    echo "⚠️  缺少依赖: ${missing_deps[*]}"
    echo "请安装: sudo apt install ${missing_deps[*]}"
else
    echo "✅ 系统依赖完整"
fi

# 检查Python
if command -v python3 >/dev/null 2>&1; then
    echo "✅ Python: $(python3 --version)"
else
    echo "⚠️  Python3 未安装"
fi

# 检查核心文件
echo "📁 检查核心文件..."
for file in xray_converter_simple.sh xray_diagnostics.sh xray_monitor.sh ss_link_utils.py; do
    if [ -f "$file" ]; then
        echo "✅ $file"
    else
        echo "❌ $file 缺失"
    fi
done

# 检查Xray
if [ -f "xray" ]; then
    if [ -x "xray" ]; then
        echo "✅ Xray二进制文件就绪"
    else
        echo "🔧 修复Xray权限..."
        chmod +x xray
        echo "✅ Xray权限已修复"
    fi
else
    echo "⚠️  Xray将在首次运行时下载"
fi

echo ""
echo "========================================"
echo "  🚀 快速启动建议"
echo "========================================"
echo ""
echo "1. 启动主程序:"
echo "   ./xray_converter_simple.sh"
echo ""
echo "2. 使用安装脚本:"
echo "   ./install_native.sh"
echo ""
echo "3. 启动监控:"
echo "   ./xray_monitor.sh start --daemon"
echo ""
echo "4. Web界面:"
echo "   cd web_prototype && pip3 install -r requirements.txt && python3 app.py"
echo ""
echo "📖 详细说明: DEPLOYMENT_GUIDE.md"
echo ""