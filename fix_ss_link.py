#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复SS链接生成和测试
"""

import base64
import urllib.parse
import socket
import json
import sys

def generate_correct_ss_link(password, server_ip, port, node_name="", method="chacha20-ietf-poly1305"):
    """生成正确格式的SS链接"""
    # 构建认证字符串: method:password
    auth_string = f"{method}:{password}"
    
    # Base64编码认证字符串
    auth_encoded = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
    
    # 构建SS链接
    ss_link = f"ss://{auth_encoded}@{server_ip}:{port}"
    
    # 添加节点名称
    if node_name:
        # URL编码节点名称
        encoded_name = urllib.parse.quote(node_name)
        ss_link += f"#{encoded_name}"
    
    return ss_link

def parse_ss_link(ss_link):
    """解析SS链接"""
    try:
        if not ss_link.startswith('ss://'):
            return None
            
        # 移除ss://前缀
        link_part = ss_link[5:]
        
        # 分离节点名称
        if '#' in link_part:
            link_part, node_name = link_part.split('#', 1)
            node_name = urllib.parse.unquote(node_name)
        else:
            node_name = ""
            
        # 分离服务器地址
        if '@' not in link_part:
            return None
            
        auth_part, server_part = link_part.split('@', 1)
        
        # 解码认证信息
        try:
            # 尝试直接解码
            try:
                auth_decoded = base64.b64decode(auth_part).decode('utf-8')
            except:
                # 如果失败，添加填充字符再试
                padding = 4 - len(auth_part) % 4
                if padding != 4:
                    auth_part += '=' * padding
                auth_decoded = base64.b64decode(auth_part).decode('utf-8')
            
            print(f"🔍 解码后的认证信息: {auth_decoded}")
            
            if ':' not in auth_decoded:
                print("❌ 认证信息中没有找到冒号分隔符")
                return None
                
            method, password = auth_decoded.split(':', 1)
            print(f"🔍 加密方法: {method}")
            print(f"🔍 密码: {password}")
        except Exception as e:
            print(f"❌ 解码认证信息失败: {e}")
            return None
            
        # 解析服务器地址和端口
        print(f"🔍 服务器部分: {server_part}")
        
        if ':' not in server_part:
            print("❌ 服务器部分没有找到冒号分隔符")
            return None
            
        server, port_str = server_part.rsplit(':', 1)
        print(f"🔍 服务器地址: {server}")
        print(f"🔍 端口字符串: {port_str}")
        
        try:
            port = int(port_str)
            print(f"🔍 端口号: {port}")
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
        print(f"解析SS链接失败: {e}")
        return None

def test_ss_connection(server, port, timeout=5):
    """测试SS服务器连接"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((server, port))
        sock.close()
        return result == 0
    except Exception:
        return False

def test_ss_link(ss_link):
    """测试SS链接"""
    print(f"🔍 测试SS链接: {ss_link}")
    
    # 解析链接
    parsed = parse_ss_link(ss_link)
    if not parsed:
        print("❌ SS链接格式无效")
        return False
        
    print(f"✅ 链接解析成功:")
    print(f"   服务器: {parsed['server']}")
    print(f"   端口: {parsed['port']}")
    print(f"   加密方法: {parsed['method']}")
    print(f"   节点名称: {parsed['node_name']}")
    
    # 测试连接
    print(f"🔍 测试连接到 {parsed['server']}:{parsed['port']}...")
    if test_ss_connection(parsed['server'], parsed['port']):
        print("✅ 连接测试成功")
        return True
    else:
        print("❌ 连接测试失败")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  生成SS链接: python3 fix_ss_link.py generate <password> <server_ip> <port> [node_name]")
        print("  测试SS链接: python3 fix_ss_link.py test <ss_link>")
        sys.exit(1)
        
    command = sys.argv[1]
    
    if command == "generate":
        if len(sys.argv) < 5:
            print("参数不足: 需要 password server_ip port [node_name]")
            sys.exit(1)
            
        password = sys.argv[2]
        server_ip = sys.argv[3]
        port = int(sys.argv[4])
        node_name = sys.argv[5] if len(sys.argv) > 5 else ""
        
        ss_link = generate_correct_ss_link(password, server_ip, port, node_name)
        print(f"生成的SS链接: {ss_link}")
        
        # 验证生成的链接
        if parse_ss_link(ss_link):
            print("✅ 链接格式验证通过")
        else:
            print("❌ 链接格式验证失败")
            
    elif command == "test":
        if len(sys.argv) < 3:
            print("参数不足: 需要 ss_link")
            sys.exit(1)
            
        ss_link = sys.argv[2]
        test_ss_link(ss_link)
        
    else:
        print(f"未知命令: {command}")
        sys.exit(1)