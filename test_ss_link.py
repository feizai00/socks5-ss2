#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SS链接测试工具
用于检测Shadowsocks链接是否可用
"""

import socket
import base64
import urllib.parse
import json
import time
import sys
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

def parse_ss_link(ss_link):
    """解析SS链接"""
    try:
        if not ss_link.startswith('ss://'):
            return None
            
        # 移除ss://前缀
        encoded_part = ss_link[5:]
        
        # 分离URL参数
        if '?' in encoded_part:
            encoded_part, params = encoded_part.split('?', 1)
        else:
            params = ''
            
        # 分离服务器地址
        if '@' in encoded_part:
            auth_part, server_part = encoded_part.split('@', 1)
        else:
            return None
            
        # 解码认证信息
        try:
            auth_decoded = base64.b64decode(auth_part + '===').decode('utf-8')
            if ':' in auth_decoded:
                method, password = auth_decoded.split(':', 1)
            else:
                return None
        except:
            return None
            
        # 解析服务器地址和端口
        if ':' in server_part:
            server, port = server_part.rsplit(':', 1)
            port = int(port)
        else:
            return None
            
        # 解析参数
        node_name = ''
        if params:
            parsed_params = urllib.parse.parse_qs(params)
            if '#' in params:
                node_name = params.split('#', 1)[1]
            elif 'group' in parsed_params:
                node_name = parsed_params['group'][0]
                
        return {
            'method': method,
            'password': password,
            'server': server,
            'port': port,
            'node_name': urllib.parse.unquote(node_name)
        }
    except Exception as e:
        return None

def test_ss_connection(server, port, timeout=10):
    """测试SS服务器连接"""
    try:
        # 创建socket连接
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        start_time = time.time()
        result = sock.connect_ex((server, port))
        end_time = time.time()
        
        sock.close()
        
        if result == 0:
            return {
                'success': True,
                'latency': round((end_time - start_time) * 1000, 2),
                'message': 'Connection successful'
            }
        else:
            return {
                'success': False,
                'latency': -1,
                'message': f'Connection failed (error code: {result})'
            }
    except socket.timeout:
        return {
            'success': False,
            'latency': -1,
            'message': 'Connection timeout'
        }
    except Exception as e:
        return {
            'success': False,
            'latency': -1,
            'message': f'Connection error: {str(e)}'
        }

def test_ss_link(ss_link, timeout=10):
    """测试SS链接"""
    result = {
        'ss_link': ss_link,
        'parsed': False,
        'connection': False,
        'details': {},
        'error': None
    }
    
    # 解析SS链接
    parsed = parse_ss_link(ss_link)
    if not parsed:
        result['error'] = 'Invalid SS link format'
        return result
        
    result['parsed'] = True
    result['details'] = parsed
    
    # 测试连接
    conn_result = test_ss_connection(parsed['server'], parsed['port'], timeout)
    result['connection'] = conn_result['success']
    result['details'].update({
        'latency': conn_result['latency'],
        'connection_message': conn_result['message']
    })
    
    return result

def test_multiple_ss_links(ss_links, timeout=10, max_workers=5):
    """批量测试SS链接"""
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_link = {
            executor.submit(test_ss_link, link, timeout): link 
            for link in ss_links
        }
        
        # 收集结果
        for future in as_completed(future_to_link):
            link = future_to_link[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                results.append({
                    'ss_link': link,
                    'parsed': False,
                    'connection': False,
                    'details': {},
                    'error': f'Test failed: {str(e)}'
                })
    
    return results

def format_test_result(result):
    """格式化测试结果"""
    ss_link = result['ss_link']
    
    if result['error']:
        return f"❌ {result['error']}"
        
    if not result['parsed']:
        return f"❌ 链接格式错误"
        
    details = result['details']
    server_info = f"{details['server']}:{details['port']}"
    node_name = details.get('node_name', 'Unknown')
    
    if result['connection']:
        latency = details.get('latency', -1)
        return f"✅ {node_name} ({server_info}) - 延迟: {latency}ms"
    else:
        message = details.get('connection_message', 'Unknown error')
        return f"❌ {node_name} ({server_info}) - {message}"

def main():
    parser = argparse.ArgumentParser(description='SS链接测试工具')
    parser.add_argument('links', nargs='*', help='SS链接')
    parser.add_argument('--file', '-f', help='从文件读取SS链接')
    parser.add_argument('--timeout', '-t', type=int, default=10, help='连接超时时间(秒)')
    parser.add_argument('--workers', '-w', type=int, default=5, help='并发测试数量')
    parser.add_argument('--json', action='store_true', help='输出JSON格式结果')
    
    args = parser.parse_args()
    
    # 收集SS链接
    ss_links = []
    
    if args.links:
        ss_links.extend(args.links)
        
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and line.startswith('ss://'):
                        ss_links.append(line)
        except Exception as e:
            print(f"读取文件失败: {e}")
            return 1
    
    if not ss_links:
        print("请提供SS链接进行测试")
        return 1
    
    print(f"🔍 开始测试 {len(ss_links)} 个SS链接...")
    print("-" * 60)
    
    # 测试链接
    results = test_multiple_ss_links(ss_links, args.timeout, args.workers)
    
    # 输出结果
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        success_count = 0
        for result in results:
            print(format_test_result(result))
            if result['connection']:
                success_count += 1
        
        print("-" * 60)
        print(f"📊 测试完成: {success_count}/{len(results)} 个链接可用")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())