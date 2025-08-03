#!/bin/bash
# 服务器端Xray服务诊断脚本

echo "=== 服务器Xray服务诊断 ==="
echo "诊断时间: $(date)"
echo ""

# 1. 检查Xray进程
echo "1. 🔍 检查Xray进程:"
xray_processes=$(ps aux | grep -v grep | grep xray)
if [ -n "$xray_processes" ]; then
    echo "✅ 发现Xray进程:"
    echo "$xray_processes" | while IFS= read -r line; do
        echo "   $line"
    done
    echo ""

    # 统计进程数量
    process_count=$(echo "$xray_processes" | wc -l)
    echo "   📊 总计: $process_count 个Xray进程"
else
    echo "❌ 未发现Xray进程"
fi
echo ""

# 2. 检查配置目录和服务
echo "2. 📁 检查配置目录:"
# 根据您的截图，配置在 /root/xray-converter/data
config_dirs=("/root/xray-converter/data" "./data" "$HOME/xray-converter/data" "$PWD/data")

found_config=false
for dir in "${config_dirs[@]}"; do
    if [ -d "$dir" ]; then
        found_config=true
        echo "✅ 发现配置目录: $dir"

        if [ -d "$dir/services" ]; then
            service_count=$(find "$dir/services" -maxdepth 1 -type d ! -path "$dir/services" 2>/dev/null | wc -l)
            echo "   └── 服务数量: $service_count"

            if [ $service_count -gt 0 ]; then
                echo "   └── 服务详情:"
                for service_dir in "$dir/services"/*; do
                    if [ -d "$service_dir" ]; then
                        port=$(basename "$service_dir")
                        pid_file="$service_dir/xray.pid"
                        config_file="$service_dir/config.json"
                        log_file="$service_dir/xray.log"

                        echo "       ┌── 端口: $port"

                        # 检查进程状态
                        if [ -f "$pid_file" ]; then
                            pid=$(cat "$pid_file" 2>/dev/null)
                            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                                echo "       ├── 状态: ✅ 运行中 (PID: $pid)"
                                # 检查端口监听
                                if netstat -tlnp 2>/dev/null | grep ":$port " >/dev/null; then
                                    echo "       ├── 端口: ✅ 正在监听"
                                else
                                    echo "       ├── 端口: ⚠️  未监听"
                                fi
                            else
                                echo "       ├── 状态: ❌ 已停止 (PID无效: $pid)"
                            fi
                        else
                            echo "       ├── 状态: ❌ 已停止 (无PID文件)"
                        fi

                        # 检查配置文件
                        if [ -f "$config_file" ]; then
                            config_size=$(du -h "$config_file" 2>/dev/null | cut -f1)
                            echo "       ├── 配置: ✅ 存在 ($config_size)"

                            # 检查配置文件语法
                            if command -v jq >/dev/null 2>&1; then
                                if jq . "$config_file" >/dev/null 2>&1; then
                                    echo "       ├── 语法: ✅ JSON格式正确"
                                else
                                    echo "       ├── 语法: ❌ JSON格式错误"
                                fi
                            fi
                        else
                            echo "       ├── 配置: ❌ 不存在"
                        fi

                        # 检查日志文件
                        if [ -f "$log_file" ]; then
                            log_size=$(du -h "$log_file" 2>/dev/null | cut -f1)
                            echo "       ├── 日志: ✅ 存在 ($log_size)"

                            # 检查最近的错误
                            recent_errors=$(tail -50 "$log_file" 2>/dev/null | grep -i "error\|failed\|fatal" | wc -l)
                            if [ "$recent_errors" -gt 0 ]; then
                                echo "       ├── 错误: ⚠️  发现 $recent_errors 个错误"
                            else
                                echo "       ├── 错误: ✅ 无错误"
                            fi

                            # 显示最后几行日志
                            echo "       └── 最新日志:"
                            tail -3 "$log_file" 2>/dev/null | while IFS= read -r line; do
                                echo "           $line"
                            done
                        else
                            echo "       └── 日志: ❌ 不存在"
                        fi
                        echo ""
                    fi
                done
            fi
        else
            echo "   └── ❌ 无services子目录"
        fi
        echo ""
    fi
done

if [ "$found_config" = false ]; then
    echo "❌ 未找到配置目录"
    echo ""
fi

# 3. 检查端口占用情况
echo "3. 🌐 检查端口占用:"
if command -v netstat >/dev/null 2>&1; then
    echo "   监听的高端口 (10000-65535):"
    netstat -tlnp 2>/dev/null | grep LISTEN | grep -E ':(1[0-9]{4}|2[0-9]{4}|3[0-9]{4}|4[0-9]{4}|5[0-9]{4}|6[0-5][0-9]{3})' | head -10 | while IFS= read -r line; do
        echo "   $line"
    done
else
    echo "   ⚠️  netstat不可用，无法检查端口"
fi
echo ""

# 4. 系统资源检查
echo "4. 💻 系统资源:"
echo "   内存使用:"
if command -v free >/dev/null 2>&1; then
    free -h | head -2 | while IFS= read -r line; do
        echo "   $line"
    done
else
    echo "   无法检查内存使用"
fi

echo ""
echo "   磁盘使用:"
df -h . 2>/dev/null | tail -1 | while IFS= read -r line; do
    echo "   $line"
done

echo ""
echo "   系统负载:"
if [ -f /proc/loadavg ]; then
    load=$(cat /proc/loadavg)
    echo "   $load"
else
    uptime | cut -d',' -f3-
fi

echo ""
echo "=== 诊断完成 ==="
echo ""

# 5. 智能建议
echo "💡 诊断建议:"

# 检查是否有停止的服务
stopped_services=0
if [ -d "/root/xray-converter/data/services" ]; then
    for service_dir in /root/xray-converter/data/services/*; do
        if [ -d "$service_dir" ]; then
            pid_file="$service_dir/xray.pid"
            if [ -f "$pid_file" ]; then
                pid=$(cat "$pid_file" 2>/dev/null)
                if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
                    stopped_services=$((stopped_services + 1))
                fi
            else
                stopped_services=$((stopped_services + 1))
            fi
        fi
    done
fi

if [ $stopped_services -gt 0 ]; then
    echo "⚠️  发现 $stopped_services 个停止的服务"
    echo "   建议: 运行主脚本选择 '2. 列出服务' 查看详情"
    echo "   或选择 '10. 自动修复' 尝试修复"
fi

echo "📋 常用操作:"
echo "   • 查看服务列表: ./xray_converter_simple.sh (选择2)"
echo "   • 查看服务详情: ./xray_converter_simple.sh (选择3)"
echo "   • 重启服务: 删除后重新添加"
echo "   • 查看实时日志: tail -f /root/xray-converter/data/services/端口号/xray.log"
echo ""
