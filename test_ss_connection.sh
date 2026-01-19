#!/bin/bash
# SS连接测试脚本

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 测试SS连接到Google
test_ss_connection() {
    local port="$1"
    local password="$2"
    local node_name="$3"
    local server_ip="$4"
    
    echo -e "${YELLOW}🧪 测试SS连接: $node_name (端口:$port)${NC}"
    
    # 测试连接Google  
    local start_time=$(date +%s)
    local response=$(timeout 10s curl -s -x socks5://127.0.0.1:$port \
        --connect-timeout 5 \
        --max-time 8 \
        -w "%{http_code}:%{time_total}" \
        http://www.google.com/generate_204 2>/dev/null)
    local end_time=$(date +%s)
    
    if [ $? -eq 0 ] && [[ "$response" == *"204"* ]]; then
        local response_time=$(echo "$response" | cut -d: -f2)
        echo -e "${GREEN}✅ 连接测试成功${NC}"
        echo "   响应时间: ${response_time}s"
        echo "   状态: 正常"
        return 0
    else
        echo -e "${RED}❌ 连接测试失败${NC}"
        echo "   错误: 无法连接到Google"
        echo "   状态: 异常"
        return 1
    fi
}

# 测试单个服务
test_single_service() {
    local port="$1"
    local service_dir="data/services/$port"
    
    if [ ! -d "$service_dir" ]; then
        echo -e "${RED}❌ 服务 $port 不存在${NC}"
        return 1
    fi
    
    # 读取服务信息
    local password=""
    local node_name="未知"
    local server_ip=$(curl -s ifconfig.me 2>/dev/null || echo "unknown")
    
    if [ -f "$service_dir/info" ]; then
        password=$(grep '^PASSWORD=' "$service_dir/info" | cut -d= -f2)
        node_name=$(grep '^NODE_NAME=' "$service_dir/info" | cut -d= -f2)
    elif [ -f "$service_dir/info.txt" ]; then
        password=$(grep '密码:' "$service_dir/info.txt" | cut -d: -f2 | xargs)
        node_name=$(grep '节点名称:' "$service_dir/info.txt" | cut -d: -f2 | xargs)
    fi
    
    if [ -z "$password" ]; then
        echo -e "${RED}❌ 无法获取服务密码${NC}"
        return 1
    fi
    
    # 检查服务是否运行
    if ! ps aux | grep -q "$port.*config.json"; then
        echo -e "${RED}❌ 服务 $port 未运行${NC}"
        return 1
    fi
    
    # 执行测试
    test_ss_connection "$port" "$password" "$node_name" "$server_ip"
}

# 测试所有服务
test_all_services() {
    echo -e "${YELLOW}🧪 测试所有SS服务连接...${NC}"
    echo "======================================="
    
    local total=0
    local success=0
    local failed=0
    
    for service_dir in data/services/*/; do
        if [ -d "$service_dir" ]; then
            local port=$(basename "$service_dir")
            total=$((total + 1))
            
            echo ""
            if test_single_service "$port"; then
                success=$((success + 1))
            else
                failed=$((failed + 1))
            fi
        fi
    done
    
    echo ""
    echo "======================================="
    echo -e "${YELLOW}📊 测试结果统计:${NC}"
    echo "总计: $total 个服务"
    echo -e "成功: ${GREEN}$success${NC} 个"
    echo -e "失败: ${RED}$failed${NC} 个"
    
    if [ $failed -eq 0 ]; then
        echo -e "${GREEN}🎉 所有服务连接正常!${NC}"
    else
        echo -e "${RED}⚠️  有 $failed 个服务连接异常，需要检查${NC}"
    fi
}

# 主程序
case "${1:-help}" in
    "test")
        if [ $# -ge 2 ]; then
            test_single_service "$2"
        else
            echo "用法: $0 test <端口>"
        fi
        ;;
    "all")
        test_all_services
        ;;
    "help"|*)
        echo "SS连接测试工具"
        echo ""
        echo "用法:"
        echo "  $0 test <端口>    - 测试指定端口的SS连接"
        echo "  $0 all           - 测试所有SS服务连接"
        echo ""
        echo "示例:"
        echo "  $0 test 22877"
        echo "  $0 all"
        ;;
esac