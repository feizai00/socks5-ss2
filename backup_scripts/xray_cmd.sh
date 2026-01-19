#!/bin/bash
# Xray命令行快捷工具 - 基于xray_converter_simple.sh

DIR="$(cd "$(dirname "$0")" && pwd)"
CONVERTER="$DIR/xray_converter_simple.sh"

# 检查converter是否存在
if [ ! -f "$CONVERTER" ]; then
    echo "错误: 找不到 xray_converter_simple.sh"
    exit 1
fi

# 帮助信息
show_help() {
    echo "Xray SOCKS5转SS 命令行工具"
    echo ""
    echo "基于 xray_converter_simple.sh 的快捷命令"
    echo ""
    echo "用法:"
    echo "  $0 <命令> [参数]"
    echo ""
    echo "命令:"
    echo "  menu                     - 启动交互式菜单 (完整功能)"
    echo "  ls                       - 快速列出所有服务"
    echo "  help                     - 显示此帮助"
    echo ""
    echo "示例:"
    echo "  $0 menu                  # 启动完整的交互式菜单"
    echo "  $0 ls                    # 快速查看服务列表"
    echo ""
    echo "注意: 完整功能请使用交互式菜单"
}

# 快速列出服务
quick_list() {
    echo "正在获取服务列表..."
    echo ""
    echo "端口    状态      节点信息"
    echo "-------------------------"
    
    SERVICE_DIR="$DIR/data/services"
    
    if [ ! -d "$SERVICE_DIR" ]; then
        echo "无服务"
        return
    fi
    
    for service_dir in "$SERVICE_DIR"/*; do
        if [ -d "$service_dir" ]; then
            port=$(basename "$service_dir")
            
            # 读取节点名称
            node_name="未知"
            if [ -f "$service_dir/info.txt" ]; then
                node_name=$(grep "节点名称:" "$service_dir/info.txt" 2>/dev/null | cut -d: -f2- | xargs || echo "未知")
            fi
            
            # 检查运行状态
            if [ -f "$service_dir/xray.pid" ] && kill -0 $(cat "$service_dir/xray.pid" 2>/dev/null) 2>/dev/null; then
                status="运行中"
            else
                status="已停止"
            fi
            
            printf "%-8s %-10s %s\n" "$port" "$status" "$node_name"
        fi
    done
    
    echo ""
    echo "要进行详细管理，请使用: $0 menu"
}

# 主程序
case "${1:-help}" in
    "menu"|"")
        echo "启动 Xray 交互式管理界面..."
        exec "$CONVERTER"
        ;;
    "ls"|"list")
        quick_list
        ;;
    "help"|"--help"|"-h")
        show_help
        ;;
    *)
        echo "未知命令: $1"
        echo ""
        show_help
        exit 1
        ;;
esac