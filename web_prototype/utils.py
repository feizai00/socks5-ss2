import re
import base64
import urllib.parse
import socket
import json
import logging
import subprocess
import tempfile
import os
import shutil
import time
import requests
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
        """测试服务器连接，返回延迟(ms)"""
        import time
        if timeout is None:
            timeout = self.timeout
            
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((server, port))
            sock.close()
            
            end_time = time.time()
            
            if result == 0:
                latency = int((end_time - start_time) * 1000)
                return latency
            else:
                return -1
        except Exception:
            return -1

    def test_proxy_connection(self, ss_port, ss_password, ss_method="aes-256-gcm", target_url="http://www.tiktok.com", timeout=10):
        """
        通过启动临时 Xray 客户端将 SS 转换为 SOCKS5，
        然后使用 requests 测试目标 URL 连通性。
        """
        # 1. 获取一个空闲的本地端口用于 SOCKS5 监听
        local_socks_port = 0
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', 0))
                local_socks_port = s.getsockname()[1]
        except Exception as e:
            logger.error(f"Failed to bind free port: {e}")
            return -1

        # 2. 生成临时 Xray 客户端配置
        # 本地 SOCKS5 -> Outbound SS (指向 127.0.0.1:ss_port)
        client_config = {
            "log": {
                "loglevel": "error"
            },
            "inbounds": [
                {
                    "port": local_socks_port,
                    "listen": "127.0.0.1",
                    "protocol": "socks",
                    "settings": {
                        "auth": "noauth",
                        "udp": True
                    }
                }
            ],
            "outbounds": [
                {
                    "protocol": "shadowsocks",
                    "settings": {
                        "servers": [
                            {
                                "address": "127.0.0.1",
                                "port": int(ss_port),
                                "method": ss_method,
                                "password": ss_password
                            }
                        ]
                    }
                }
            ]
        }

        # 3. 写入临时配置文件
        tmp_dir = tempfile.mkdtemp()
        config_path = os.path.join(tmp_dir, f'test_config_{ss_port}_{int(time.time())}.json')
        
        try:
            with open(config_path, 'w') as f:
                json.dump(client_config, f)

            # 4. 启动临时 Xray 进程
            xray_bin = current_app.config.get('XRAY_BIN_PATH', 'xray')
            process = subprocess.Popen(
                [xray_bin, 'run', '-config', config_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # 等待进程启动
            time.sleep(1) 
            
            # 5. 使用 requests 发送请求
            proxies = {
                'http': f'socks5h://127.0.0.1:{local_socks_port}',
                'https': f'socks5h://127.0.0.1:{local_socks_port}'
            }
            
            start_time = time.time()
            try:
                # 使用 Session 以便复用连接
                resp = requests.get(target_url, proxies=proxies, timeout=timeout)
                # 检查响应状态码，如果返回数据说明通了
                # 用户要求: "如果返回数据就说明是正常的"
                if resp.status_code < 500: # 只要不是服务器错误，或者连接错误，都算通
                    end_time = time.time()
                    latency = int((end_time - start_time) * 1000)
                    return latency
                else:
                    return -1
            except Exception as e:
                # logger.error(f"Proxy test failed: {e}")
                return -1
            finally:
                # 6. 清理进程
                process.terminate()
                try:
                    process.wait(timeout=2)
                except:
                    process.kill()

        except Exception as e:
            logger.error(f"Test setup failed: {e}")
            return -1
        finally:
            # 7. 清理临时文件
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)
