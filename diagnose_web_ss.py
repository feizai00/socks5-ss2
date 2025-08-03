#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web端SS链接诊断工具
"""

import sys
import os
import json
import base64
import urllib.parse
import socket
import requests

def get_server_ip():
    """获取服务器IP地址"""
    # 尝试多个服务获取外网IP
    services = [
        "https://ifconfig.me/ip",
        "https://ipinfo.io/ip", 
        "https://icanhazip.com",
        "https://ident.me",
        "https://api.ipify.org",
        "https://checkip.amazonaws.com"
    ]
    
    print("🔍 获取服务器IP地址...")
    for service in services:
        try:
            print(f"   尝试: {service}")
            response = requests.get(service, timeout=10)
            if response.status_code == 200:
                ip = response.text.strip()
                # 验证IP格式
                socket.inet_aton(ip)
                print(f"✅ 获取到外网IP: {ip}")
                return ip
        except Exception as e:
            print(f"   失败: {e}")
            continue
    
    # 如果外网服务都失败，尝试获取本机IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        if local_ip != "127.0.0.1":
            print(f"✅ 获取到本机IP: {local_ip}")
            return local_ip
    except Exception as e:
        print(f"   本机IP获取失败: {e}")
    
    print("❌ 无法获取服务器IP")
    return "YOUR_SERVER_IP"

def generate_ss_link(password, server_ip, port, node_name=""):
    """生成Shadowsocks链接"""
    method = "chacha20-ietf-poly1305"
    
    print(f"🔍 生成SS链接参数:")
    print(f"   加密方法: {method}")
    print(f"   密码: {password}")
    print(f"   服务器IP: {server_ip}")
    print(f"   端口: {port}")
    print(f"   节点名称: {node_name}")
    
    # 编码认证信息
    auth_string = f"{method}:{password}"
    auth_encoded = base64.b64encode(auth_string.encode()).decode()
    
    print(f"   认证字符串: {auth_string}")
    print(f"   Base64编码: {auth_encoded}")
    
    # 生成完整的SS链接
    ss_link = f"ss://{auth_encoded}@{server_ip}:{port}"
    
    # 添加节点名称
    if node_name:
        encoded_name = urllib.parse.quote(node_name)
        ss_link += f"#{encoded_name}"
        print(f"   编码节点名: {encoded_name}")
    
    print(f"✅ 生成的SS链接: {ss_link}")
    return ss_link

def test_ss_connection(server, port, timeout=10):
    """测试SS服务器连接"""
    try:
        print(f"🔍 测试连接到 {server}:{port}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((server, port))
        sock.close()
        
        if result == 0:
            print(f"✅ 端口 {port} 连接成功")
            return True
        else:
            print(f"❌ 端口 {port} 连接失败 (错误码: {result})")
            return False
    except Exception as e:
        print(f"❌ 连接测试异常: {e}")
        return False

def parse_ss_link(ss_link):
    """解析SS链接"""
    try:
        print(f"🔍 解析SS链接: {ss_link}")
        
        if not ss_link.startswith('ss://'):
            print("❌ 不是有效的SS链接格式")
            return None
            
        # 移除ss://前缀
        link_part = ss_link[5:]
        print(f"   链接部分: {link_part}")
        
        # 分离节点名称
        if '#' in link_part:
            link_part, node_name = link_part.split('#', 1)
            node_name = urllib.parse.unquote(node_name)
            print(f"   节点名称: {node_name}")
        else:
            node_name = ""
            
        # 移除可能的路径部分（斜杠）
        if link_part.endswith('/'):
            link_part = link_part[:-1]
            print(f"   移除斜杠后: {link_part}")
            
        # 分离服务器地址
        if '@' not in link_part:
            print("❌ 链接格式错误：缺少@分隔符")
            return None
            
        auth_part, server_part = link_part.split('@', 1)
        print(f"   认证部分: {auth_part}")
        print(f"   服务器部分: {server_part}")
        
        # 解码认证信息
        try:
            auth_decoded = base64.b64decode(auth_part).decode('utf-8')
            print(f"   解码认证信息: {auth_decoded}")
            
            if ':' not in auth_decoded:
                print("❌ 认证信息格式错误")
                return None
                
            method, password = auth_decoded.split(':', 1)
            print(f"   加密方法: {method}")
            print(f"   密码: {password}")
        except Exception as e:
            print(f"❌ 解码认证信息失败: {e}")
            return None
            
        # 解析服务器地址和端口
        if ':' not in server_part:
            print("❌ 服务器部分格式错误")
            return None
            
        server, port_str = server_part.rsplit(':', 1)
        print(f"   服务器地址: {server}")
        print(f"   端口字符串: {port_str}")
        
        try:
            port = int(port_str)
            print(f"   端口号: {port}")
        except ValueError as e:
            print(f"❌ 端口转换失败: {e}")
            return None
            
        return {
            'method': method,
            'password': password,
            'server': server,
            'port': port,
            'node_name': node_name
        }
        
    except Exception as e:
        print(f"❌ 解析SS链接失败: {e}")
        return None

def check_service_config(port):
    """检查服务配置文件"""
    config_path = f"data/services/{port}/config.json"
    print(f"🔍 检查服务配置: {config_path}")
    
    if not os.path.exists(config_path):
        print(f"❌ 配置文件不存在: {config_path}")
        return None
        
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        print("✅ 配置文件读取成功")
        print(f"   入站配置: {config.get('inbounds', [])}")
        print(f"   出站配置: {config.get('outbounds', [])}")
        
        # 检查入站端口
        inbounds = config.get('inbounds', [])
        if inbounds:
            inbound_port = inbounds[0].get('port')
            print(f"   入站端口: {inbound_port}")
            
            if str(inbound_port) != str(port):
                print(f"⚠️  端口不匹配: 配置文件 {inbound_port} vs 期望 {port}")
                
        return config
        
    except Exception as e:
        print(f"❌ 读取配置文件失败: {e}")
        return None

def diagnose_service(port):
    """诊断指定端口的服务"""
    print(f"\n{'='*60}")
    print(f"🔍 诊断服务端口: {port}")
    print(f"{'='*60}")
    
    # 1. 检查配置文件
    config = check_service_config(port)
    if not config:
        return False
        
    # 2. 获取服务器IP
    server_ip = get_server_ip()
    if server_ip == "YOUR_SERVER_IP":
        print("❌ 无法获取服务器IP，SS链接将不可用")
        return False
        
    # 3. 从配置文件中提取SS密码
    inbounds = config.get('inbounds', [])
    if not inbounds:
        print("❌ 配置文件中没有入站配置")
        return False
        
    inbound = inbounds[0]
    settings = inbound.get('settings', {})
    password = settings.get('password')
    
    if not password:
        print("❌ 配置文件中没有找到密码")
        return False
        
    print(f"✅ 从配置文件获取密码: {password}")
    
    # 4. 生成SS链接
    ss_link = generate_ss_link(password, server_ip, port, f"port_{port}")
    
    # 5. 解析验证SS链接
    parsed = parse_ss_link(ss_link)
    if not parsed:
        print("❌ SS链接解析失败")
        return False
        
    print("✅ SS链接解析成功")
    
    # 6. 测试连接
    if test_ss_connection(server_ip, port):
        print("✅ 服务连接测试成功")
        return True
    else:
        print("❌ 服务连接测试失败")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 diagnose_web_ss.py <port>")
        print("示例: python3 diagnose_web_ss.py 29657")
        sys.exit(1)
        
    port = sys.argv[1]
    success = diagnose_service(port)
    
    if success:
        print(f"\n🎉 端口 {port} 的SS链接诊断通过！")
    else:
        print(f"\n❌ 端口 {port} 的SS链接存在问题，需要修复")
        sys.exit(1)