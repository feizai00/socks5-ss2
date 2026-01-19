#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一的SS链接工具 - 生成、解析、测试一体化
整合了之前的多个SS链接处理脚本的功能
"""

import base64
import urllib.parse
import socket
import json
import sys
import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

class SSLinkUtils:
    """SS链接工具类"""
    
    def __init__(self):
        self.default_method = "chacha20-ietf-poly1305"
        self.timeout = 5
    
    def generate_ss_link(self, password, server_ip, port, node_name="", method=None):
        """生成正确格式的SS链接"""
        if method is None:
            method = self.default_method
            
        # 构建认证字符串: method:password
        auth_string = f"{method}:{password}"
        
        # Base64编码认证字符串
        auth_encoded = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
        
        # 构建SS链接
        ss_link = f"ss://{auth_encoded}@{server_ip}:{port}"
        
        # 添加节点名称
        if node_name:
            encoded_name = urllib.parse.quote(node_name)
            ss_link += f"#{encoded_name}"
        
        return ss_link
    
    def parse_ss_link(self, ss_link, verbose=False):
        """解析SS链接"""
        try:
            if not ss_link.startswith('ss://'):
                if verbose:
                    print("❌ 无效的SS链接格式")
                return None
                
            # 移除ss://前缀
            link_part = ss_link[5:]
            if verbose:
                print(f"🔍 链接部分: {link_part}")
            
            # 分离节点名称
            node_name = ""
            if '#' in link_part:
                link_part, node_name = link_part.split('#', 1)
                node_name = urllib.parse.unquote(node_name)
                if verbose:
                    print(f"🔍 节点名称: {node_name}")
            
            # 分离服务器地址
            if '@' in link_part:
                auth_part, server_part = link_part.split('@', 1)
            else:
                if verbose:
                    print("❌ 链接格式错误：缺少@符号")
                return None
            
            # 解码认证信息
            try:
                # 添加填充字符以确保正确解码
                padding = '=' * (4 - len(auth_part) % 4)
                auth_decoded = base64.b64decode(auth_part + padding).decode('utf-8')
                if ':' in auth_decoded:
                    method, password = auth_decoded.split(':', 1)
                else:
                    if verbose:
                        print("❌ 认证信息格式错误")
                    return None
            except Exception as e:
                if verbose:
                    print(f"❌ Base64解码失败: {e}")
                return None
            
            # 解析服务器地址和端口
            if ':' in server_part:
                # 处理IPv6地址的情况
                if server_part.startswith('[') and ']:' in server_part:
                    # IPv6格式: [::1]:8080
                    server, port = server_part.rsplit(']:', 1)
                    server = server[1:]  # 移除开头的[
                else:
                    # IPv4格式: 1.2.3.4:8080
                    server, port = server_part.rsplit(':', 1)
                
                try:
                    port = int(port)
                except ValueError:
                    if verbose:
                        print(f"❌ 端口号无效: {port}")
                    return None
            else:
                if verbose:
                    print("❌ 服务器地址格式错误：缺少端口号")
                return None
            
            result = {
                'method': method,
                'password': password,
                'server': server,
                'port': port,
                'node_name': node_name
            }
            
            if verbose:
                print(f"✅ 解析成功:")
                print(f"   方法: {method}")
                print(f"   密码: {password}")
                print(f"   服务器: {server}")
                print(f"   端口: {port}")
                print(f"   节点名: {node_name}")
            
            return result
            
        except Exception as e:
            if verbose:
                print(f"❌ 解析失败: {e}")
            return None
    
    def test_connection(self, server, port, timeout=None):
        """测试服务器连接"""
        if timeout is None:
            timeout = self.timeout
            
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((server, port))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    def test_ss_link(self, ss_link, timeout=None):
        """测试SS链接可用性"""
        config = self.parse_ss_link(ss_link)
        if not config:
            return False, "链接解析失败"
        
        is_reachable = self.test_connection(config['server'], config['port'], timeout)
        status = "可达" if is_reachable else "不可达"
        
        return is_reachable, {
            'status': status,
            'server': config['server'],
            'port': config['port'],
            'method': config['method'],
            'node_name': config['node_name']
        }
    
    def batch_test_links(self, ss_links, max_workers=10):
        """批量测试SS链接"""
        results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_link = {
                executor.submit(self.test_ss_link, link): link 
                for link in ss_links
            }
            
            for future in as_completed(future_to_link):
                link = future_to_link[future]
                try:
                    is_reachable, result = future.result()
                    results.append({
                        'link': link,
                        'reachable': is_reachable,
                        'result': result
                    })
                except Exception as e:
                    results.append({
                        'link': link,
                        'reachable': False,
                        'result': f"测试失败: {e}"
                    })
        
        return results

def main():
    """命令行接口"""
    parser = argparse.ArgumentParser(description='SS链接工具')
    parser.add_argument('action', choices=['generate', 'parse', 'test', 'batch-test'],
                       help='操作类型')
    parser.add_argument('--password', '-p', help='密码')
    parser.add_argument('--server', '-s', help='服务器地址')
    parser.add_argument('--port', '-P', type=int, help='端口')
    parser.add_argument('--method', '-m', help='加密方法')
    parser.add_argument('--name', '-n', help='节点名称')
    parser.add_argument('--link', '-l', help='SS链接')
    parser.add_argument('--links', '-L', nargs='+', help='多个SS链接')
    parser.add_argument('--file', '-f', help='包含SS链接的文件')
    parser.add_argument('--timeout', '-t', type=int, default=5, help='连接超时时间')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    args = parser.parse_args()
    utils = SSLinkUtils()
    utils.timeout = args.timeout
    
    if args.action == 'generate':
        if not all([args.password, args.server, args.port]):
            print("❌ 生成链接需要提供密码、服务器和端口")
            sys.exit(1)
        
        link = utils.generate_ss_link(
            args.password, args.server, args.port,
            args.name or "", args.method
        )
        print(f"✅ 生成的SS链接: {link}")
    
    elif args.action == 'parse':
        if not args.link:
            print("❌ 解析需要提供SS链接")
            sys.exit(1)
        
        result = utils.parse_ss_link(args.link, args.verbose)
        if result:
            print("✅ 解析结果:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("❌ 解析失败")
            sys.exit(1)
    
    elif args.action == 'test':
        if not args.link:
            print("❌ 测试需要提供SS链接")
            sys.exit(1)
        
        is_reachable, result = utils.test_ss_link(args.link, args.timeout)
        if is_reachable:
            print("✅ 连接测试通过")
        else:
            print("❌ 连接测试失败")
        
        if isinstance(result, dict):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(result)
    
    elif args.action == 'batch-test':
        links = []
        
        if args.links:
            links.extend(args.links)
        
        if args.file:
            try:
                with open(args.file, 'r', encoding='utf-8') as f:
                    file_links = [line.strip() for line in f if line.strip()]
                    links.extend(file_links)
            except Exception as e:
                print(f"❌ 读取文件失败: {e}")
                sys.exit(1)
        
        if not links:
            print("❌ 没有提供测试链接")
            sys.exit(1)
        
        print(f"🔍 开始测试 {len(links)} 个链接...")
        results = utils.batch_test_links(links)
        
        passed = sum(1 for r in results if r['reachable'])
        print(f"\n📊 测试结果: {passed}/{len(results)} 通过")
        
        for result in results:
            status = "✅" if result['reachable'] else "❌"
            print(f"{status} {result['link']}")
            if args.verbose and isinstance(result['result'], dict):
                print(f"   {json.dumps(result['result'], ensure_ascii=False)}")

if __name__ == '__main__':
    main()