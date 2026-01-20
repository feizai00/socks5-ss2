import re
import base64
import urllib.parse
import socket
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import request, session, current_app
from database import get_db

import hashlib

logger = logging.getLogger(__name__)

def verify_user(username, password):
    """简化的用户验证函数"""
    try:
        # 清理输入
        username = username.strip()

        # 连接数据库
        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE username = ?',
            (username,)
        ).fetchone()

        if not user:
            logger.warning(f"登录失败: 用户 '{username}' 不存在")
            return False, "用户名不存在"

        # 验证密码
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if user['password_hash'] != password_hash:
            logger.warning(f"登录失败: 用户 '{username}' 密码错误")
            
            return False, "密码错误"

        logger.info(f"登录成功: 用户 '{username}'")
        return True, user

    except Exception as e:
        logger.error(f"用户验证异常: {e}")
        return False, "系统错误"

def log_operation(action, target=None, details=None):
    """记录操作日志"""
    try:
        db = get_db()
        user_id = session.get('user_id')
        ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        user_agent = request.headers.get('User-Agent', '')

        db.execute('''
            INSERT INTO operation_logs (user_id, action, target, details, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, action, target, details, ip_address, user_agent))
        db.commit()
    except Exception as e:
        logger.error(f"记录操作日志失败: {e}")

def validate_input(data, rules):
    """输入验证"""
    errors = {}

    for field, rule_list in rules.items():
        value = data.get(field, '')

        for rule in rule_list:
            if rule == 'required' and not value:
                errors[field] = f'{field} 是必填项'
                break
            elif rule.startswith('min_length:'):
                min_len = int(rule.split(':')[1])
                if len(str(value)) < min_len:
                    errors[field] = f'{field} 最少需要 {min_len} 个字符'
                    break
            elif rule.startswith('max_length:'):
                max_len = int(rule.split(':')[1])
                if len(str(value)) > max_len:
                    errors[field] = f'{field} 最多 {max_len} 个字符'
                    break
            elif rule == 'email':
                email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                if value and not re.match(email_pattern, value):
                    errors[field] = f'{field} 格式不正确'
                    break
            elif rule == 'port':
                try:
                    port = int(value)
                    if not (1 <= port <= 65535):
                        errors[field] = f'{field} 必须在 1-65535 之间'
                        break
                except ValueError:
                    errors[field] = f'{field} 必须是有效的端口号'
                    break
            elif rule == 'ip':
                ip_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
                if value and not re.match(ip_pattern, value):
                    errors[field] = f'{field} 不是有效的IP地址'
                    break

    return errors

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
                return None
                
            # 移除ss://前缀
            link_part = ss_link[5:]
            
            # 分离节点名称
            node_name = ""
            if '#' in link_part:
                link_part, node_name = link_part.split('#', 1)
                node_name = urllib.parse.unquote(node_name)
            
            # 分离服务器地址
            if '@' in link_part:
                auth_part, server_part = link_part.split('@', 1)
            else:
                return None
            
            # 解码认证信息
            try:
                # 添加填充字符以确保正确解码
                padding = '=' * (4 - len(auth_part) % 4)
                auth_decoded = base64.b64decode(auth_part + padding).decode('utf-8')
                if ':' in auth_decoded:
                    method, password = auth_decoded.split(':', 1)
                else:
                    return None
            except Exception:
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
                    return None
            else:
                return None
            
            result = {
                'method': method,
                'password': password,
                'server': server,
                'port': port,
                'node_name': node_name
            }
            
            return result
            
        except Exception:
            return None
    
    def test_connection(self, server, port, timeout=None):
        """测试服务器连接，通过代理访问 tiktok.com 返回延迟(ms)"""
        import time
        import requests
        
        if timeout is None:
            timeout = 10  # 增加超时时间以适应实际网络请求
            
        try:
            # 构造代理配置
            # 使用 socks5h:// 协议让 DNS 解析也通过代理，防止 DNS 污染
            proxy_url = f'socks5h://{server}:{port}'
            proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            start_time = time.time()
            
            # 请求 tiktok.com
            # verify=False 忽略 SSL 证书验证，专注于连通性测试
            response = requests.get(
                'https://www.tiktok.com', 
                proxies=proxies, 
                headers=headers, 
                timeout=timeout,
                verify=False
            )
            
            end_time = time.time()
            
            # 只要能收到响应，就说明链路是通的
            if response.status_code > 0:
                latency = int((end_time - start_time) * 1000)
                return latency
            else:
                return -1
                
        except Exception as e:
            # 记录详细错误以便调试
            logger.debug(f"代理测试失败 {server}:{port} - {str(e)}")
            return -1
