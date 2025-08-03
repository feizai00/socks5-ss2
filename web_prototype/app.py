#!/usr/bin/env python3
"""
Xray转换器Web管理系统
生产级Flask应用，完整的前后端功能实现
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, g
from functools import wraps
import os
import subprocess
import sqlite3
import threading
import time
import logging
import secrets
import re
import shutil
import json
from datetime import datetime, timedelta
import hashlib
import base64
import urllib.parse
import socket
import subprocess

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('xray_web.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # 生产级密钥

# 配置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
XRAY_SCRIPT = os.path.join(PARENT_DIR, 'xray_converter_simple.sh')
SERVICE_DIR = os.path.join(PARENT_DIR, 'data', 'services')
DB_PATH = os.path.join(SCRIPT_DIR, 'xray_web.db')
UPLOAD_FOLDER = os.path.join(SCRIPT_DIR, 'uploads')
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

# 确保目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Flask配置
app.config.update(
    UPLOAD_FOLDER=UPLOAD_FOLDER,
    MAX_CONTENT_LENGTH=MAX_CONTENT_LENGTH,
    SESSION_COOKIE_SECURE=False,  # 生产环境应设为True
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=24)
)

def get_db():
    """获取数据库连接"""
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db():
    """关闭数据库连接"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

@app.teardown_appcontext
def close_db_context(error):
    close_db()

def init_db():
    """初始化数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 创建用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            role TEXT DEFAULT 'user',
            is_active BOOLEAN DEFAULT 1,
            last_login TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 创建服务表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            port INTEGER UNIQUE NOT NULL,
            node_name TEXT NOT NULL,
            socks_ip TEXT NOT NULL,
            socks_port INTEGER NOT NULL,
            socks_user TEXT,
            socks_pass TEXT,
            ss_password TEXT NOT NULL,
            method TEXT DEFAULT 'aes-256-gcm',
            expires_at INTEGER DEFAULT 0,
            status TEXT DEFAULT 'stopped',
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
    ''')

    # 创建操作日志表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            target TEXT,
            details TEXT,
            ip_address TEXT,
            user_agent TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # 创建监控数据表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monitor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_port INTEGER,
            cpu_usage REAL,
            memory_usage REAL,
            connections INTEGER,
            traffic_in INTEGER DEFAULT 0,
            traffic_out INTEGER DEFAULT 0,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (service_port) REFERENCES services (port)
        )
    ''')

    # 创建系统设置表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 数据库迁移：添加删除时间字段
    try:
        cursor.execute('ALTER TABLE services ADD COLUMN deleted_at TIMESTAMP DEFAULT NULL')
    except sqlite3.OperationalError:
        # 字段已存在，忽略错误
        pass

    # 创建索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_services_port ON services (port)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_services_status ON services (status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_services_deleted ON services (deleted_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_operation_logs_user ON operation_logs (user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_operation_logs_timestamp ON operation_logs (timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_monitor_data_service ON monitor_data (service_port)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_monitor_data_timestamp ON monitor_data (timestamp)')

    # 创建默认管理员用户 (admin/admin123)
    admin_hash = hashlib.sha256('admin123'.encode()).hexdigest()
    cursor.execute('''
        INSERT OR IGNORE INTO users (username, password_hash, role, email)
        VALUES (?, ?, ?, ?)
    ''', ('admin', admin_hash, 'admin', 'admin@localhost'))

    # 插入默认系统设置
    default_settings = [
        ('site_name', 'Xray转换器管理系统', '网站名称'),
        ('max_services_per_user', '50', '每用户最大服务数'),
        ('default_service_expiry', '30', '默认服务有效期(天)'),
        ('enable_registration', 'false', '是否允许用户注册'),
        ('monitor_interval', '30', '监控检查间隔(秒)'),
        ('log_retention_days', '30', '日志保留天数'),
    ]

    for key, value, desc in default_settings:
        cursor.execute('''
            INSERT OR IGNORE INTO system_settings (key, value, description)
            VALUES (?, ?, ?)
        ''', (key, value, desc))

    conn.commit()
    conn.close()
    logger.info("数据库初始化完成")

# 认证装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))

        db = get_db()
        user = db.execute(
            'SELECT role FROM users WHERE id = ?', (session['user_id'],)
        ).fetchone()

        if not user or user['role'] != 'admin':
            flash('需要管理员权限', 'error')
            return redirect(url_for('index'))

        return f(*args, **kwargs)
    return decorated_function

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

def sync_filesystem_to_db():
    """同步文件系统中的服务到数据库"""
    try:
        if not os.path.exists(SERVICE_DIR):
            return

        db = get_db()

        # 获取数据库中已有的端口
        existing_ports = set()
        db_services = db.execute('SELECT port FROM services').fetchall()
        for service in db_services:
            existing_ports.add(str(service['port']))

        # 扫描文件系统中的服务
        for port_dir in os.listdir(SERVICE_DIR):
            port_path = os.path.join(SERVICE_DIR, port_dir)
            if os.path.isdir(port_path) and port_dir not in existing_ports:
                # 读取服务信息
                info_txt_file = os.path.join(port_path, 'info.txt')
                config_env_file = os.path.join(port_path, 'config.env')

                node_name = f'服务{port_dir}'
                password = 'unknown'

                if os.path.exists(info_txt_file):
                    with open(info_txt_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if ':' in line:
                                key, value = line.split(':', 1)
                                key = key.strip()
                                value = value.strip()
                                if key == '节点名称':
                                    node_name = value
                                elif key == 'Shadowsocks密码':
                                    password = value
                elif os.path.exists(config_env_file):
                    with open(config_env_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            if '=' in line:
                                key, value = line.strip().split('=', 1)
                                if key == 'NODE_NAME':
                                    node_name = value
                                elif key == 'PASSWORD':
                                    password = value

                # 添加到数据库
                try:
                    db.execute('''
                        INSERT INTO services (
                            port, ss_password, node_name, socks_ip, socks_port,
                            method, created_by, created_at, expires_at, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        int(port_dir), password, node_name, '127.0.0.1', 1080,
                        'chacha20-ietf-poly1305', 1, datetime.now().isoformat(), 0, 'stopped'
                    ))
                    logger.info(f"同步服务到数据库: 端口 {port_dir}")
                except Exception as e:
                    logger.error(f"同步服务 {port_dir} 到数据库失败: {e}")

        db.commit()
    except Exception as e:
        logger.error(f"同步文件系统到数据库失败: {e}")

def get_services():
    """获取所有服务信息"""
    services = []

    # 暂时直接使用文件系统方法，避免数据库同步问题
    logger.info("直接从文件系统获取服务信息")
    return get_services_from_filesystem()

    # 先同步文件系统到数据库
    try:
        sync_filesystem_to_db()
    except Exception as e:
        logger.error(f"同步失败，使用文件系统备用方法: {e}")

    # 从数据库获取服务信息
    try:
        db = get_db()
        db_services = db.execute('''
            SELECT s.*, u.username as created_by_name
            FROM services s
            LEFT JOIN users u ON s.created_by = u.id
            ORDER BY s.port
        ''').fetchall()

        for db_service in db_services:
            service = dict(db_service)

            # 检查文件系统中的实际状态
            port_path = os.path.join(SERVICE_DIR, str(service['port']))
            if os.path.isdir(port_path):
                # 检查服务状态
                pid_file = os.path.join(port_path, 'xray.pid')
                if os.path.exists(pid_file):
                    try:
                        with open(pid_file, 'r') as f:
                            pid = int(f.read().strip())
                        # 检查进程是否存在
                        try:
                            os.kill(pid, 0)
                            service['status'] = 'running'
                        except OSError:
                            service['status'] = 'stopped'
                    except:
                        service['status'] = 'stopped'
                else:
                    service['status'] = 'stopped'

                # 检查是否过期
                if service['expires_at'] and service['expires_at'] != 0:
                    if datetime.now().timestamp() > service['expires_at']:
                        service['status'] = 'expired'
            else:
                service['status'] = 'missing'

            # 更新数据库中的状态
            if service['status'] != db_service['status']:
                db.execute(
                    'UPDATE services SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    (service['status'], service['id'])
                )

        db.commit()
        services = [dict(s) for s in db_services]

    except Exception as e:
        logger.error(f"从数据库获取服务失败: {e}")
        # 回退到文件系统方式
        services = get_services_from_filesystem()

    return services

def get_services_from_filesystem():
    """从文件系统获取服务信息（备用方法）"""
    services = []
    if not os.path.exists(SERVICE_DIR):
        return services

    for port_dir in os.listdir(SERVICE_DIR):
        port_path = os.path.join(SERVICE_DIR, port_dir)
        if os.path.isdir(port_path):
            # 尝试读取info.txt文件 (新格式)
            info_txt_file = os.path.join(port_path, 'info.txt')
            config_env_file = os.path.join(port_path, 'config.env')
            info_file = os.path.join(port_path, 'info')

            service = {'port': port_dir}

            # 优先读取info.txt文件 (新格式)
            if os.path.exists(info_txt_file):
                with open(info_txt_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if ':' in line:
                            key, value = line.split(':', 1)
                            key = key.strip()
                            value = value.strip()
                            # 转换为标准字段名
                            if key == '节点名称':
                                service['node_name'] = value
                            elif key == 'Shadowsocks端口':
                                service['ss_port'] = value
                            elif key == 'Shadowsocks密码':
                                service['ss_password'] = value
                            elif key == 'SOCKS5后端':
                                service['socks_backend'] = value
                            elif key == '状态':
                                service['file_status'] = value
                            elif key == '有效期':
                                service['expires_display'] = value
                            elif key == '创建时间':
                                service['created_at'] = value
                            elif key == '协议':
                                service['protocol'] = value
                            elif key == '加密方式':
                                service['encryption'] = value
                            elif key == 'SOCKS5认证':
                                service['socks_auth'] = value

            # 读取config.env文件获取详细配置
            elif os.path.exists(config_env_file):
                with open(config_env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if '=' in line:
                            key, value = line.strip().split('=', 1)
                            service[key.lower()] = value

            # 兼容旧格式info文件
            elif os.path.exists(info_file):
                with open(info_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if '=' in line:
                            key, value = line.strip().split('=', 1)
                            service[key.lower()] = value

            # 如果没有找到任何信息文件，跳过
            else:
                continue

            # 设置默认值
            if 'node_name' not in service:
                service['node_name'] = service.get('node_name', f'服务{port_dir}')

            # 检查服务状态
            pid_file = os.path.join(port_path, 'xray.pid')
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, 'r') as f:
                        pid = int(f.read().strip())
                    # 检查进程是否存在
                    try:
                        os.kill(pid, 0)
                        service['status'] = 'running'
                    except OSError:
                        service['status'] = 'stopped'
                except:
                    service['status'] = 'stopped'
            else:
                # 新创建的服务默认为stopped状态
                service['status'] = 'stopped'

            # 检查是否过期
            if 'expires_at' in service and service['expires_at'] != '0':
                try:
                    expires_at = int(service['expires_at'])
                    if datetime.now().timestamp() > expires_at:
                        service['status'] = 'expired'
                except:
                    pass

            # 确保有必要的字段用于显示
            if 'ss_port' not in service and 'port' in service:
                service['ss_port'] = service['port']

            # 解析SOCKS5后端地址为IP和端口
            if 'socks_backend' in service and service['socks_backend']:
                try:
                    if ':' in service['socks_backend']:
                        socks_ip, socks_port = service['socks_backend'].split(':', 1)
                        service['socks_ip'] = socks_ip
                        service['socks_port'] = socks_port
                    else:
                        service['socks_ip'] = service['socks_backend']
                        service['socks_port'] = ''
                except:
                    service['socks_ip'] = service['socks_backend']
                    service['socks_port'] = ''

            # 处理有效期显示
            if 'expires_display' in service:
                if service['expires_display'] == '永久':
                    service['expires_at'] = '0'
                else:
                    # 如果是其他格式，尝试解析为时间戳
                    service['expires_at'] = service.get('expires_at', '0')

            # 生成SS链接
            if service.get('ss_password') and service.get('port'):
                server_ip = get_server_ip()
                ss_link = generate_ss_link(
                    service['ss_password'], 
                    server_ip, 
                    service['port'], 
                    service.get('node_name', '')
                )
                service['ss_link'] = ss_link
                service['server_ip'] = server_ip
            
            services.append(service)

    return sorted(services, key=lambda x: int(x['port']))

def get_server_ip():
    """获取服务器IP地址"""
    import socket
    import requests
    
    # 尝试多个服务获取外网IP
    services = [
        "https://ifconfig.me/ip",
        "https://ipinfo.io/ip", 
        "https://icanhazip.com",
        "https://ident.me",
        "https://api.ipify.org",
        "https://checkip.amazonaws.com"
    ]
    
    for service in services:
        try:
            response = requests.get(service, timeout=10)
            if response.status_code == 200:
                ip = response.text.strip()
                # 验证IP格式
                socket.inet_aton(ip)
                return ip
        except:
            continue
    
    # 如果外网服务都失败，尝试获取本机IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        if local_ip != "127.0.0.1":
            return local_ip
    except:
        pass
    
    return "YOUR_SERVER_IP"

def generate_ss_link(password, server_ip, port, node_name=""):
    """生成Shadowsocks链接"""
    method = "chacha20-ietf-poly1305"
    
    # 编码认证信息
    auth_string = f"{method}:{password}"
    auth_encoded = base64.b64encode(auth_string.encode()).decode()
    
    # 生成完整的SS链接 (修复格式问题)
    ss_link = f"ss://{auth_encoded}@{server_ip}:{port}"
    
    # 添加节点名称
    if node_name:
        encoded_name = urllib.parse.quote(node_name)
        ss_link += f"#{encoded_name}"
    
    logger.info(f"生成SS链接: {ss_link}")
    return ss_link

def validate_port(port):
    """验证并标准化端口号"""
    if isinstance(port, str):
        if not port.isdigit():
            return None, '无效的端口号'
        port = int(port)
    elif not isinstance(port, int):
        return None, '无效的端口号'
        
    # 确保端口在有效范围内
    if not (1 <= port <= 65535):
        return None, '端口号必须在1-65535范围内'
        
    return port, None

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
            
        # 移除可能的路径部分（斜杠）
        if link_part.endswith('/'):
            link_part = link_part[:-1]
            
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
            
            if ':' not in auth_decoded:
                return None
                
            method, password = auth_decoded.split(':', 1)
        except Exception as e:
            logger.error(f"解码认证信息失败: {e}")
            return None
            
        # 解析服务器地址和端口
        if ':' not in server_part:
            return None
            
        server, port_str = server_part.rsplit(':', 1)
        
        try:
            port = int(port_str)
        except ValueError as e:
            logger.error(f"端口转换失败: {e}")
            return None
            
        return {
            'method': method,
            'password': password,
            'server': server,
            'port': port,
            'node_name': node_name
        }
        
    except Exception as e:
        logger.error(f"解析SS链接失败: {e}")
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

def build_socks_server_config(socks_ip, socks_port, socks_user, socks_pass):
    """构建SOCKS服务器配置"""
    config = {
        "address": socks_ip,
        "port": socks_port
    }
    
    # 只有在有用户名和密码时才添加认证信息
    if socks_user and socks_pass:
        config["users"] = [
            {
                "user": socks_user,
                "pass": socks_pass
            }
        ]
    
    return config

def call_xray_script(action, *args, timeout=60):
    """调用Xray脚本"""
    try:
        cmd = ['bash', XRAY_SCRIPT, action] + list(args)
        logger.info(f"执行命令: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=PARENT_DIR
        )

        logger.info(f"命令执行结果: 返回码={result.returncode}")
        if result.stdout:
            logger.info(f"标准输出: {result.stdout}")
    
        if result.stderr:
            logger.warning(f"标准错误: {result.stderr}")

        return result.returncode == 0, result.stdout, result.stderr

    except subprocess.TimeoutExpired:
        logger.error(f"脚本执行超时: {action}")
        return False, '', f'脚本执行超时 ({timeout}秒)'
    except FileNotFoundError:
        logger.error(f"脚本文件不存在: {XRAY_SCRIPT}")
        return False, '', '脚本文件不存在'
    except Exception as e:
        logger.error(f"脚本执行异常: {e}")
        return False, '', str(e)

def sync_service_to_db(port, service_data):
    """同步服务信息到数据库"""
    try:
        db = get_db()

        # 检查服务是否已存在
        existing = db.execute('SELECT id FROM services WHERE port = ?', (str(port),)).fetchone()

        if existing:
            # 更新现有服务
            db.execute('''
                UPDATE services SET
                    node_name = ?, socks_ip = ?, socks_port = ?,
                    socks_user = ?, socks_pass = ?, ss_password = ?,
                    expires_at = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE port = ?
            ''', (
                service_data.get('node_name', ''),
                service_data.get('socks_ip', ''),
                service_data.get('socks_port', 0),
                service_data.get('socks_user', ''),
                service_data.get('socks_pass', ''),
                service_data.get('password', ''),
                service_data.get('expires_at', 0),
                service_data.get('status', 'stopped'),
                str(port)
            ))
        else:
            # 创建新服务
            db.execute('''
                INSERT INTO services (
                    port, node_name, socks_ip, socks_port,
                    socks_user, socks_pass, ss_password,
                    expires_at, status, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                str(port),
                service_data.get('node_name', ''),
                service_data.get('socks_ip', ''),
                service_data.get('socks_port', 0),
                service_data.get('socks_user', ''),
                service_data.get('socks_pass', ''),
                service_data.get('password', ''),
                service_data.get('expires_at', 0),
                service_data.get('status', 'stopped'),
                session.get('user_id')
            ))

        db.commit()
        return True

    except Exception as e:
        logger.error(f"同步服务到数据库失败: {e}")
        return False

def get_system_stats():
    """获取系统统计信息"""
    try:
        # CPU使用率
        cpu_usage = 0
        try:
            with open('/proc/loadavg', 'r') as f:
                load_avg = float(f.read().split()[0])
                cpu_usage = min(load_avg * 100, 100)
        except:
            pass

        # 内存使用率
        memory_usage = 0
        try:
            with open('/proc/meminfo', 'r') as f:
                lines = f.readlines()
                mem_total = int([line for line in lines if 'MemTotal' in line][0].split()[1])
                mem_available = int([line for line in lines if 'MemAvailable' in line][0].split()[1])
                memory_usage = ((mem_total - mem_available) / mem_total) * 100
        except:
            pass

        # 磁盘使用率
        disk_usage = 0
        try:
            total, used, _ = shutil.disk_usage(SCRIPT_DIR)
            disk_usage = (used / total) * 100
        except:
            pass

        # 网络连接数
        connections = 0
        try:
            result = subprocess.run(['netstat', '-an'], capture_output=True, text=True)
            if result.returncode == 0:
                connections = len([line for line in result.stdout.split('\n') if 'ESTABLISHED' in line])
        except:
            pass

        return {
            'cpu_usage': round(cpu_usage, 1),
            'memory_usage': round(memory_usage, 1),
            'disk_usage': round(disk_usage, 1),
            'connections': connections,
            'timestamp': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"获取系统统计失败: {e}")
        return {
            'cpu_usage': 0,
            'memory_usage': 0,
            'disk_usage': 0,
            'connections': 0,
            'timestamp': datetime.now().isoformat()
        }

# 登录路由
@app.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # 基本输入验证
        if not username:
            flash('请输入用户名', 'error')
            return render_template('login.html')

        if not password:
            flash('请输入密码', 'error')
            return render_template('login.html')

        # 使用简化的验证函数
        success, result = verify_user(username, password)

        if success:
            user = result
            # 设置会话
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session.permanent = True

            # 更新最后登录时间
            try:
                db = get_db()
                db.execute(
                    'UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?',
                    (user['id'],)
                )
                db.commit()
            except Exception as e:
                logger.error(f"更新登录时间失败: {e}")

            # 记录登录日志
            log_operation('login', 'system', f'用户 {username} 登录成功')

            flash('登录成功！', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            # 登录失败
            error_message = result
            log_operation('login_failed', 'system', f'用户 {username} 登录失败: {error_message}')
            flash(error_message, 'error')

    return render_template('login.html')

@app.route('/logout')
def logout():
    """用户登出"""
    username = session.get('username', 'unknown')
    log_operation('logout', 'system', f'用户 {username} 登出')

    session.clear()
    flash('已安全登出', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """主页"""
    try:
        services = get_services()
        logger.info(f"获取到 {len(services)} 个服务")
        for service in services:
            logger.info(f"服务: {service}")

        # 统计信息
        total = len(services)
        running = len([s for s in services if s.get('status') == 'running'])
        stopped = len([s for s in services if s.get('status') == 'stopped'])
        expired = len([s for s in services if s.get('status') == 'expired'])

        stats = {
            'total': total,
            'running': running,
            'stopped': stopped,
            'expired': expired
        }

        # 获取系统统计
        system_stats = get_system_stats()

        return render_template('index.html',
                             services=services,
                             stats=stats,
                             system_stats=system_stats)
    except Exception as e:
        logger.error(f"主页加载失败: {e}")
        flash('加载数据失败，请刷新页面', 'error')
        return render_template('index.html',
                             services=[],
                             stats={'total': 0, 'running': 0, 'stopped': 0, 'expired': 0},
                             system_stats={})

@app.route('/api/services')
@login_required
def api_services():
    """API: 获取服务列表"""
    try:
        services = get_services()
        return jsonify({
            'success': True,
            'data': services,
            'count': len(services)
        })
    except Exception as e:
        logger.error(f"API获取服务列表失败: {e}")
        return jsonify({
            'success': False,
            'error': '获取服务列表失败',
            'message': str(e)
        }), 500

@app.route('/api/services', methods=['POST'])
@login_required
def api_create_service():
    """API: 创建新服务"""
    try:
        data = request.get_json()

        # 输入验证
        errors = validate_input(data, {
            'node_name': ['required', 'min_length:1', 'max_length:100'],
            'socks_ip': ['required', 'ip'],
            'socks_port': ['required', 'port'],
            'ss_password': ['required', 'min_length:8']
        })

        if errors:
            return jsonify({
                'success': False,
                'error': '输入验证失败',
                'errors': errors
            }), 400

        # 检查端口是否已被使用
        db = get_db()
        existing_port = db.execute(
            'SELECT port FROM services WHERE port = ?',
            (data.get('port'),)
        ).fetchone()

        if existing_port:
            return jsonify({
                'success': False,
                'error': '端口已被使用'
            }), 400

        # 调用Shell脚本创建服务
        # 这里需要根据实际的Shell脚本接口进行调整
        success, stdout, stderr = call_xray_script('add_service_api',
                                                  data['node_name'],
                                                  f"{data['socks_ip']}:{data['socks_port']}:{data.get('socks_user', '')}:{data.get('socks_pass', '')}",
                                                  data.get('expiry_type', 'permanent'))

        if success:
            # 同步到数据库
            service_data = {
                'node_name': data['node_name'],
                'socks_ip': data['socks_ip'],
                'socks_port': data['socks_port'],
                'socks_user': data.get('socks_user', ''),
                'socks_pass': data.get('socks_pass', ''),
                'password': data['ss_password'],
                'expires_at': data.get('expires_at', 0),
                'status': 'stopped'
            }

            sync_service_to_db(data['port'], service_data)

            # 记录操作日志
            log_operation('create_service', f"port_{data['port']}",
                         f"创建服务: {data['node_name']}")

            return jsonify({
                'success': True,
                'message': '服务创建成功',
                'port': data['port']
            })
        else:
            return jsonify({
                'success': False,
                'error': '服务创建失败',
                'message': stderr or stdout
            }), 500

    except Exception as e:
        logger.error(f"API创建服务失败: {e}")
        return jsonify({
            'success': False,
            'error': '服务创建失败',
            'message': str(e)
        }), 500

@app.route('/api/services/<port>/start', methods=['POST'])
@app.route('/api/services/<int:port>/start', methods=['POST'])
@login_required
def api_start_service(port):
    """API: 启动服务"""
    try:
        # 验证端口
        port, error = validate_port(port)
        if error:
            return jsonify({
                'success': False,
                'error': error
            }), 400

        # 检查服务是否存在 (优先从文件系统检查)
        service_dir = os.path.join(SERVICE_DIR, str(port))
        if not os.path.exists(service_dir):
            return jsonify({
                'success': False,
                'error': '服务不存在'
            }), 404

        # 尝试从数据库获取服务信息，如果不存在则从文件系统获取
        db = get_db()
        service = db.execute(
            'SELECT * FROM services WHERE port = ?', (str(port),)
        ).fetchone()

        # 如果数据库中没有记录，从文件系统获取基本信息
        if not service:
            info_file = os.path.join(service_dir, 'info.txt')
            if os.path.exists(info_file):
                # 创建一个模拟的service对象
                service = {
                    'port': port,
                    'expires_at': None,  # 文件系统服务默认不过期
                    'status': 'stopped'
                }
            else:
                return jsonify({
                    'success': False,
                    'error': '服务配置不完整'
                }), 404

        # 检查是否过期
        if service['expires_at'] and service['expires_at'] != 0:
            if datetime.now().timestamp() > service['expires_at']:
                return jsonify({
                    'success': False,
                    'error': '服务已过期，请先续费'
                }), 400

        # 调用Shell脚本启动服务
        success, stdout, stderr = call_xray_script('start_single_service', str(port))

        if success:
            # 尝试更新数据库状态 (如果数据库中有记录)
            try:
                db = get_db()
                db.execute(
                    'UPDATE services SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE port = ?',
                    ('running', str(port))
                )
                db.commit()
            except Exception:
                # 数据库操作失败不影响主要功能
                pass

            # 记录操作日志
            log_operation('start_service', f'port_{port}', f'启动服务端口 {port}')

            return jsonify({
                'success': True,
                'message': f'服务端口 {port} 启动成功'
            })
        else:
            # 尝试更新数据库状态 (如果数据库中有记录)
            try:
                db = get_db()
                db.execute(
                    'UPDATE services SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE port = ?',
                    ('stopped', str(port))
                )
                db.commit()
            except Exception:
                # 数据库操作失败不影响主要功能
                pass

            return jsonify({
                'success': False,
                'error': '服务启动失败',
                'message': stderr or stdout
            }), 500

    except Exception as e:
        logger.error(f"API启动服务失败: {e}")
        return jsonify({
            'success': False,
            'error': '服务启动失败',
            'message': str(e)
        }), 500

@app.route('/api/services/<port>/stop', methods=['POST'])
@app.route('/api/services/<int:port>/stop', methods=['POST'])
@login_required
def api_stop_service(port):
    """API: 停止服务"""
    try:
        # 验证端口
        port, error = validate_port(port)
        if error:
            return jsonify({
                'success': False,
                'error': error
            }), 400

        # 检查服务是否存在 (优先从文件系统检查)
        service_dir = os.path.join(SERVICE_DIR, str(port))
        if not os.path.exists(service_dir):
            return jsonify({
                'success': False,
                'error': '服务不存在'
            }), 404

        # 停止服务
        pid_file = os.path.join(SERVICE_DIR, str(port), 'xray.pid')
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())

                # 尝试优雅停止
                os.kill(pid, 15)  # SIGTERM
                time.sleep(1)

                # 检查是否还在运行
                try:
                    os.kill(pid, 0)
                    # 如果还在运行，强制终止
                    os.kill(pid, 9)  # SIGKILL
                except OSError:
                    pass  # 进程已经停止

                # 删除PID文件
                if os.path.exists(pid_file):
                    os.remove(pid_file)

                success = True
                message = f'服务端口 {port} 停止成功'

            except (ValueError, OSError) as e:
                success = False
                message = f'停止服务失败: {str(e)}'
        else:
            success = True
            message = f'服务端口 {port} 已经停止'

        # 尝试更新数据库状态 (如果数据库中有记录)
        try:
            db = get_db()
            db.execute(
                'UPDATE services SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE port = ?',
                ('stopped', str(port))
            )
            db.commit()
        except Exception:
            # 数据库操作失败不影响主要功能
            pass

        if success:
            # 记录操作日志
            log_operation('stop_service', f'port_{port}', f'停止服务端口 {port}')

            return jsonify({
                'success': True,
                'message': message
            })
        else:
            return jsonify({
                'success': False,
                'error': '服务停止失败',
                'message': message
            }), 500

    except Exception as e:
        logger.error(f"API停止服务失败: {e}")
        return jsonify({
            'success': False,
            'error': '服务停止失败',
            'message': str(e)
        }), 500



@app.route('/api/services/<port>/restart', methods=['POST'])
@app.route('/api/services/<int:port>/restart', methods=['POST'])
@login_required
def api_restart_service(port):
    """API: 重启服务"""
    try:
        # 验证端口
        port, error = validate_port(port)
        if error:
            return jsonify({
                'success': False,
                'error': error
            }), 400

        # 检查服务是否存在
        db = get_db()
        service = db.execute(
            'SELECT * FROM services WHERE port = ?', (str(port),)
        ).fetchone()

        if not service:
            return jsonify({
                'success': False,
                'error': '服务不存在'
            }), 404

        # 先停止服务
        stop_response = api_stop_service(port)
        if not stop_response.get_json().get('success', False):
            return stop_response

        # 等待一秒
        time.sleep(2)

        # 再启动服务
        start_response = api_start_service(port)

        if start_response.get_json().get('success', False):
            # 记录操作日志
            log_operation('restart_service', f'port_{port}', f'重启服务端口 {port}')

            return jsonify({
                'success': True,
                'message': f'服务端口 {port} 重启成功'
            })
        else:
            return start_response

    except Exception as e:
        logger.error(f"API重启服务失败: {e}")
        return jsonify({
            'success': False,
            'error': '服务重启失败',
            'message': str(e)
        }), 500

@app.route('/api/services/<port>/test-ss', methods=['POST'])
@app.route('/api/services/<int:port>/test-ss', methods=['POST'])
@login_required
def api_test_ss_link(port):
    """API: 测试SS链接"""
    try:
        # 验证端口
        port, error = validate_port(port)
        if error:
            return jsonify({
                'success': False,
                'error': error
            }), 400

        # 获取服务信息
        services = get_services_from_filesystem()
        service = None
        for s in services:
            if s['port'] == str(port):
                service = s
                break
        
        if not service:
            return jsonify({
                'success': False,
                'error': '服务不存在'
            }), 404
            
        # 检查是否有SS链接
        ss_link = service.get('ss_link')
        if not ss_link:
            return jsonify({
                'success': False,
                'error': 'SS链接不存在'
            }), 400
            
        # 测试SS链接
        test_result = test_ss_link(ss_link, timeout=10)
        
        # 格式化结果
        if test_result['connection']:
            latency = test_result['details'].get('latency', -1)
            message = f"连接成功，延迟: {latency}ms"
            status = 'success'
        else:
            message = test_result['details'].get('connection_message', '连接失败')
            if test_result['error']:
                message = test_result['error']
            status = 'error'
            
        # 记录操作日志
        log_operation('test_ss_link', f'port_{port}', 
                     f'测试SS链接: {service["node_name"]} - {message}')
        
        return jsonify({
            'success': test_result['connection'],
            'status': status,
            'message': message,
            'details': {
                'server': test_result['details'].get('server', ''),
                'port': test_result['details'].get('port', 0),
                'latency': test_result['details'].get('latency', -1),
                'parsed': test_result['parsed']
            }
        })
        
    except Exception as e:
        logger.error(f"API测试SS链接失败: {e}")
        return jsonify({
            'success': False,
            'error': 'SS链接测试失败',
            'message': str(e)
        }), 500

@app.route('/api/test-ss-batch', methods=['POST'])
@login_required
def api_test_ss_batch():
    """API: 批量测试SS链接"""
    try:
        data = request.get_json()
        if not data or 'ports' not in data:
            return jsonify({
                'success': False,
                'error': '缺少端口列表'
            }), 400
            
        ports = data['ports']
        if not isinstance(ports, list):
            return jsonify({
                'success': False,
                'error': '端口列表格式错误'
            }), 400
            
        # 获取所有服务
        services = get_services_from_filesystem()
        service_dict = {s['port']: s for s in services}
        
        results = []
        for port in ports:
            port_str = str(port)
            if port_str not in service_dict:
                results.append({
                    'port': port,
                    'success': False,
                    'message': '服务不存在'
                })
                continue
                
            service = service_dict[port_str]
            ss_link = service.get('ss_link')
            if not ss_link:
                results.append({
                    'port': port,
                    'success': False,
                    'message': 'SS链接不存在'
                })
                continue
                
            # 测试链接
            test_result = test_ss_link(ss_link, timeout=10)
            
            if test_result['connection']:
                latency = test_result['details'].get('latency', -1)
                message = f"连接成功，延迟: {latency}ms"
            else:
                message = test_result['details'].get('connection_message', '连接失败')
                if test_result['error']:
                    message = test_result['error']
                    
            results.append({
                'port': port,
                'node_name': service.get('node_name', f'服务{port}'),
                'success': test_result['connection'],
                'message': message,
                'latency': test_result['details'].get('latency', -1),
                'server': test_result['details'].get('server', ''),
                'server_port': test_result['details'].get('port', 0)
            })
        
        # 统计结果
        success_count = sum(1 for r in results if r['success'])
        total_count = len(results)
        
        return jsonify({
            'success': True,
            'results': results,
            'summary': {
                'total': total_count,
                'success': success_count,
                'failed': total_count - success_count
            }
        })
        
    except Exception as e:
        logger.error(f"API批量测试SS链接失败: {e}")
        return jsonify({
            'success': False,
            'error': '批量测试失败',
            'message': str(e)
        }), 500

@app.route('/api/services/<port>', methods=['DELETE'])
@login_required
def api_delete_service(port):
    """API: 删除服务"""
    try:
        # 验证端口
        port, error = validate_port(port)
        if error:
            return jsonify({
                'success': False,
                'error': error
            }), 400

        # 检查服务是否存在 (先检查文件系统，再检查数据库)
        service_dir = os.path.join(SERVICE_DIR, str(port))
        if not os.path.exists(service_dir):
            return jsonify({
                'success': False,
                'error': '服务不存在'
            }), 404
            
        # 尝试从数据库获取服务信息
        db = get_db()
        service = db.execute(
            'SELECT * FROM services WHERE port = ?', (str(port),)
        ).fetchone()

        # 如果数据库中没有记录，从文件系统创建临时记录
        if not service:
            service = {
                'port': str(port),
                'node_name': f'服务{port}',
                'created_by': session.get('user_id', 'admin')
            }

        # 检查权限（非管理员只能删除自己创建的服务）
        if session.get('role') != 'admin' and service.get('created_by') != session.get('user_id'):
            return jsonify({
                'success': False,
                'error': '权限不足'
            }), 403

        # 先停止服务
        call_xray_script('stop_single_service', str(port))

        # 移动服务文件到回收站目录而不是直接删除
        service_dir = os.path.join(SERVICE_DIR, str(port))
        if os.path.exists(service_dir):
            recycle_dir = os.path.join(SERVICE_DIR, '.recycle')
            os.makedirs(recycle_dir, exist_ok=True)
            
            import time
            timestamp = int(time.time())
            recycled_name = f"{port}_{timestamp}"
            recycled_path = os.path.join(recycle_dir, recycled_name)
            
            shutil.move(service_dir, recycled_path)
            logger.info(f"服务文件已移动到回收站: {recycled_path}")

        # 软删除：在数据库中标记为已删除
        if 'id' in service:  # 只有数据库中的服务才执行此操作
            db.execute(
                'UPDATE services SET status = ?, deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE port = ?',
                ('deleted', str(port))
            )
            db.commit()

        # 记录操作日志
        log_operation('delete_service', f'port_{port}',
                     f'删除服务: {service["node_name"]} (端口 {port})')

        return jsonify({
            'success': True,
            'message': f'服务端口 {port} 删除成功'
        })

    except Exception as e:
        logger.error(f"API删除服务失败: {e}")
        return jsonify({
            'success': False,
            'error': '服务删除失败',
            'message': str(e)
        }), 500

@app.route('/api/services/<port>/logs')
@login_required
def api_get_service_logs(port):
    """API: 获取服务日志"""
    try:
        # 验证端口
        if not port.isdigit():
            return jsonify({
                'success': False,
                'error': '无效的端口号'
            }), 400

        log_file = os.path.join(SERVICE_DIR, port, 'xray.log')

        if not os.path.exists(log_file):
            return jsonify({
                'success': True,
                'data': '暂无日志内容'
            })

        # 读取最后100行日志
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                last_lines = lines[-100:] if len(lines) > 100 else lines
                log_content = ''.join(last_lines)
        except UnicodeDecodeError:
            # 如果UTF-8解码失败，尝试其他编码
            with open(log_file, 'r', encoding='latin-1') as f:
                lines = f.readlines()
                last_lines = lines[-100:] if len(lines) > 100 else lines
                log_content = ''.join(last_lines)

        return jsonify({
            'success': True,
            'data': log_content
        })

    except Exception as e:
        logger.error(f"API获取服务日志失败: {e}")
        return jsonify({
            'success': False,
            'error': '获取日志失败',
            'message': str(e)
        }), 500

@app.route('/api/services/<port>/logs', methods=['DELETE'])
@login_required
def api_clear_service_logs(port):
    """API: 清空服务日志"""
    try:
        # 验证端口
        if not port.isdigit():
            return jsonify({
                'success': False,
                'error': '无效的端口号'
            }), 400

        log_file = os.path.join(SERVICE_DIR, port, 'xray.log')

        if os.path.exists(log_file):
            # 清空日志文件
            with open(log_file, 'w') as f:
                f.write('')

        # 记录操作日志
        log_operation('clear_logs', f'port_{port}', f'清空服务端口 {port} 的日志')

        return jsonify({
            'success': True,
            'message': '日志已清空'
        })

    except Exception as e:
        logger.error(f"API清空服务日志失败: {e}")
        return jsonify({
            'success': False,
            'error': '清空日志失败',
            'message': str(e)
        }), 500

@app.route('/api/monitor/stats')
@login_required
def api_monitor_stats():
    """API: 获取监控统计"""
    try:
        # 获取系统统计
        system_stats = get_system_stats()

        # 获取服务统计
        services = get_services()
        service_stats = {
            'total': len(services),
            'running': len([s for s in services if s.get('status') == 'running']),
            'stopped': len([s for s in services if s.get('status') == 'stopped']),
            'expired': len([s for s in services if s.get('status') == 'expired'])
        }

        # 保存监控数据到数据库
        try:
            db = get_db()
            db.execute('''
                INSERT INTO monitor_data (cpu_usage, memory_usage, connections, timestamp)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                system_stats['cpu_usage'],
                system_stats['memory_usage'],
                system_stats['connections']
            ))
            db.commit()
        except Exception as e:
            logger.warning(f"保存监控数据失败: {e}")

        return jsonify({
            'success': True,
            'data': {
                'system': system_stats,
                'services': service_stats,
                'timestamp': datetime.now().isoformat()
            }
        })

    except Exception as e:
        logger.error(f"API获取监控统计失败: {e}")
        return jsonify({
            'success': False,
            'error': '获取监控统计失败',
            'message': str(e)
        }), 500

@app.route('/api/monitor/history')
@login_required
def api_monitor_history():
    """API: 获取监控历史数据"""
    try:
        hours = request.args.get('hours', 24, type=int)

        db = get_db()
        history_data = db.execute('''
            SELECT cpu_usage, memory_usage, connections, timestamp
            FROM monitor_data
            WHERE timestamp > datetime('now', '-{} hours')
            ORDER BY timestamp DESC
            LIMIT 100
        '''.format(hours)).fetchall()

        data = []
        for row in history_data:
            data.append({
                'cpu_usage': row['cpu_usage'],
                'memory_usage': row['memory_usage'],
                'connections': row['connections'],
                'timestamp': row['timestamp']
            })

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        logger.error(f"API获取监控历史失败: {e}")
        return jsonify({
            'success': False,
            'error': '获取监控历史失败',
            'message': str(e)
        }), 500

@app.route('/service/<port>')
@app.route('/service/<int:port>')
@login_required
def service_detail(port):
    """服务详情页"""
    try:
        # 验证端口
        port, error = validate_port(port)
        if error:
            flash(error, 'error')
            return redirect(url_for('index'))

        # 从数据库获取服务信息
        db = get_db()
        service = db.execute('''
            SELECT s.*, u.username as created_by_name
            FROM services s
            LEFT JOIN users u ON s.created_by = u.id
            WHERE s.port = ?
        ''', (str(port),)).fetchone()

        if not service:
            flash('服务不存在', 'error')
            return redirect(url_for('index'))

        # 转换为字典并检查实际状态
        service_dict = dict(service)

        # 检查实际运行状态
        pid_file = os.path.join(SERVICE_DIR, str(port), 'xray.pid')
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                try:
                    os.kill(pid, 0)
                    service_dict['status'] = 'running'
                except OSError:
                    service_dict['status'] = 'stopped'
            except:
                service_dict['status'] = 'stopped'
        else:
            service_dict['status'] = 'stopped'

        # 检查是否过期
        if service_dict['expires_at'] and service_dict['expires_at'] != 0:
            if datetime.now().timestamp() > service_dict['expires_at']:
                service_dict['status'] = 'expired'

        # 获取服务器IP
        try:
            import socket
            hostname = socket.gethostname()
            server_ip = socket.gethostbyname(hostname)
        except:
            server_ip = '127.0.0.1'

        service_dict['server_ip'] = server_ip

        return render_template('service_detail.html', service=service_dict)

    except Exception as e:
        logger.error(f"服务详情页加载失败: {e}")
        flash('加载服务详情失败', 'error')
        return redirect(url_for('index'))







@app.route('/service/<port>/edit')
@app.route('/service/<int:port>/edit')
@login_required
def edit_service(port):
    """编辑服务页"""
    try:
        # 验证端口
        port, error = validate_port(port)
        if error:
            flash(error, 'error')
            return redirect(url_for('index'))

        # 从数据库获取服务信息
        db = get_db()
        service = db.execute('''
            SELECT s.*, u.username as created_by_name
            FROM services s
            LEFT JOIN users u ON s.created_by = u.id
            WHERE s.port = ?
        ''', (str(port),)).fetchone()

        if not service:
            flash('服务不存在', 'error')
            return redirect(url_for('index'))

        # 检查权限（非管理员只能编辑自己创建的服务）
        if session.get('role') != 'admin' and service['created_by'] != session.get('user_id'):
            flash('权限不足', 'error')
            return redirect(url_for('service_detail', port=port))

        return render_template('edit_service.html', service=dict(service))

    except Exception as e:
        logger.error(f"编辑服务页加载失败: {e}")
        flash('加载编辑页面失败', 'error')
        return redirect(url_for('index'))

@app.route('/service/<port>/update', methods=['POST'])
@app.route('/service/<int:port>/update', methods=['POST'])
@login_required
def update_service(port):
    """更新服务"""
    try:
        # 验证端口
        port, error = validate_port(port)
        if error:
            flash(error, 'error')
            return redirect(url_for('index'))

        # 检查服务是否存在
        db = get_db()
        service = db.execute(
            'SELECT * FROM services WHERE port = ?', (str(port),)
        ).fetchone()

        if not service:
            flash('服务不存在', 'error')
            return redirect(url_for('index'))

        # 检查权限
        if session.get('role') != 'admin' and service['created_by'] != session.get('user_id'):
            flash('权限不足', 'error')
            return redirect(url_for('service_detail', port=port))

        # 获取表单数据
        node_name = request.form.get('node_name', '').strip()
        socks_ip = request.form.get('socks_ip', '').strip()
        socks_port = request.form.get('socks_port', '').strip()
        socks_user = request.form.get('socks_user', '').strip()
        socks_pass = request.form.get('socks_pass', '').strip()
        ss_password = request.form.get('ss_password', '').strip()
        expiry_type = request.form.get('expiry_type', 'permanent')
        custom_days = request.form.get('custom_days', '').strip()

        # 输入验证
        errors = validate_input(request.form, {
            'node_name': ['required', 'min_length:1', 'max_length:100'],
            'socks_ip': ['required', 'ip'],
            'socks_port': ['required', 'port'],
            'ss_password': ['required', 'min_length:8']
        })

        if errors:
            for error in errors.values():
                flash(error, 'error')
            return redirect(url_for('edit_service', port=port))

        # 计算过期时间
        expires_at = 0
        if expiry_type == 'permanent':
            expires_at = 0
        elif expiry_type == 'custom' and custom_days:
            try:
                days = int(custom_days)
                expires_at = int((datetime.now() + timedelta(days=days)).timestamp())
            except ValueError:
                flash('自定义天数必须是数字', 'error')
                return redirect(url_for('edit_service', port=port))
        else:
            days_map = {'7days': 7, '30days': 30, '90days': 90}
            days = days_map.get(expiry_type, 0)
            if days:
                expires_at = int((datetime.now() + timedelta(days=days)).timestamp())

        # 更新数据库
        db.execute('''
            UPDATE services SET
                node_name = ?, socks_ip = ?, socks_port = ?,
                socks_user = ?, socks_pass = ?, ss_password = ?,
                expires_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE port = ?
        ''', (
            node_name, socks_ip, int(socks_port),
            socks_user, socks_pass, ss_password,
            expires_at, str(port)
        ))
        db.commit()

        # 更新配置文件
        info_file = os.path.join(SERVICE_DIR, str(port), 'info')
        if os.path.exists(info_file):
            # 读取现有信息
            info_data = {}
            with open(info_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        info_data[key] = value

            # 更新信息
            info_data.update({
                'NODE_NAME': node_name,
                'SOCKS_IP': socks_ip,
                'SOCKS_PORT': socks_port,
                'SOCKS_USER': socks_user,
                'SOCKS_PASS': socks_pass,
                'PASSWORD': ss_password,
                'EXPIRES_AT': str(expires_at),
                'EDITED': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'EDITED_AT': str(int(datetime.now().timestamp()))
            })

            # 写回文件
            with open(info_file, 'w', encoding='utf-8') as f:
                for key, value in info_data.items():
                    f.write(f'{key}={value}\n')

        # 重新生成配置文件
        success, stdout, stderr = call_xray_script('regenerate_config', port)

        # 记录操作日志
        log_operation('update_service', f'port_{port}',
                     f'更新服务: {node_name}')

        flash('服务更新成功', 'success')
        return redirect(url_for('service_detail', port=port))

    except Exception as e:
        logger.error(f"更新服务失败: {e}")
        flash(f'更新失败: {str(e)}', 'error')
        return redirect(url_for('edit_service', port=port))

@app.route('/add_service', methods=['GET', 'POST'])
@login_required
def add_service():
    """添加服务"""
    if request.method == 'POST':
        try:
            # 获取表单数据
            node_name = request.form.get('node_name', '').strip()
            socks_input = request.form.get('socks_input', '').strip()

            # 验证输入
            if not node_name:
                flash('节点名称不能为空', 'error')
                return render_template('add_service.html')

            if not socks_input:
                flash('SOCKS5代理信息不能为空', 'error')
                return render_template('add_service.html')

            # 解析SOCKS5输入
            socks_parts = socks_input.split(':')
            if len(socks_parts) < 2:
                flash('SOCKS5代理格式错误，正确格式: IP:端口 或 IP:端口:用户名:密码', 'error')
                return render_template('add_service.html')

            socks_ip = socks_parts[0]
            socks_port = socks_parts[1]
            socks_user = socks_parts[2] if len(socks_parts) > 2 else ""
            socks_pass = socks_parts[3] if len(socks_parts) > 3 else ""

            # 验证SOCKS5端口
            try:
                socks_port_int = int(socks_port)
                if socks_port_int < 1 or socks_port_int > 65535:
                    flash('SOCKS5端口范围必须在1-65535之间', 'error')
                    return render_template('add_service.html')
            except ValueError:
                flash('SOCKS5端口必须是数字', 'error')
                return render_template('add_service.html')

            # 自动生成SS端口和密码
            import random
            import string

            # 生成随机端口 (避免冲突)
            max_attempts = 50
            for attempt in range(max_attempts):
                ss_port = random.randint(10000, 65535)
                if not os.path.exists(os.path.join(SERVICE_DIR, str(ss_port))):
                    break
            else:
                flash('无法生成可用端口，请稍后重试', 'error')
                return render_template('add_service.html')

            # 生成随机密码
            ss_password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))

            # 检查端口是否已存在 (双重检查)
            if os.path.exists(os.path.join(SERVICE_DIR, str(ss_port))):
                flash(f'端口 {ss_port} 已被使用，请重试', 'error')
                return render_template('add_service.html')

            # 创建服务目录
            service_dir = os.path.join(SERVICE_DIR, str(ss_port))
            os.makedirs(service_dir, exist_ok=True)

            # 创建配置文件
            config_file = os.path.join(service_dir, 'config.env')
            with open(config_file, 'w') as f:
                f.write(f'PORT={ss_port}\n')
                f.write(f'PASSWORD={ss_password}\n')
                f.write(f'NODE_NAME={node_name}\n')
                f.write(f'SOCKS_IP={socks_ip}\n')
                f.write(f'SOCKS_PORT={socks_port}\n')
                f.write(f'SOCKS_USER={socks_user}\n')
                f.write(f'SOCKS_PASS={socks_pass}\n')
                f.write(f'CREATED_AT={datetime.now().isoformat()}\n')
                f.write(f'CREATED_BY={session.get("username", "admin")}\n')

            # 生成Xray配置文件 (SOCKS5转SS)
            config_file = os.path.join(service_dir, 'config.json')
            config_data = {
                "log": {
                    "loglevel": "warning"
                },
                "inbounds": [
                    {
                        "port": ss_port,
                        "protocol": "shadowsocks",
                        "settings": {
                            "method": "chacha20-ietf-poly1305",
                            "password": ss_password
                        }
                    }
                ],
                "outbounds": [
                    {
                        "protocol": "socks",
                        "settings": {
                            "servers": [
                                build_socks_server_config(socks_ip, int(socks_port), socks_user, socks_pass)
                            ]
                        }
                    }
                ]
            }

            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2)

            # 保存服务信息文件
            info_file = os.path.join(service_dir, 'info.txt')
            with open(info_file, 'w') as f:
                f.write(f'节点名称: {node_name}\n')
                f.write(f'Shadowsocks端口: {ss_port}\n')
                f.write(f'Shadowsocks密码: {ss_password}\n')
                f.write(f'协议: Shadowsocks\n')
                f.write(f'加密方式: chacha20-ietf-poly1305\n')
                f.write(f'SOCKS5后端: {socks_ip}:{socks_port}\n')
                if socks_user and socks_pass:
                    f.write(f'SOCKS5认证: {socks_user}:{socks_pass}\n')
                else:
                    f.write(f'SOCKS5认证: 无\n')
                f.write(f'创建时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
                f.write(f'有效期: 永久\n')
                f.write(f'状态: 已创建\n')

            # 保存到数据库
            try:
                db = get_db()
                current_user_id = session.get('user_id', 1)  # 默认为admin用户

                db.execute('''
                    INSERT INTO services (
                        port, ss_password, node_name, socks_ip, socks_port,
                        method, created_by, created_at, expires_at, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    ss_port, ss_password, node_name, socks_ip, socks_port,
                    'chacha20-ietf-poly1305', current_user_id, datetime.now().isoformat(), 0, 'stopped'
                ))
                db.commit()
                logger.info(f"服务已保存到数据库: 端口 {ss_port}")
            except Exception as db_error:
                logger.error(f"保存到数据库失败: {db_error}")
                # 继续执行，不影响文件创建

            # 自动启动服务
            try:
                logger.info(f"正在自动启动新添加的服务: 端口 {ss_port}")
                success, stdout, stderr = call_xray_script('start_single_service', str(ss_port))
                
                if success:
                    # 更新数据库状态为运行中
                    try:
                        db = get_db()
                        db.execute(
                            'UPDATE services SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE port = ?',
                            ('running', str(ss_port))
                        )
                        db.commit()
                        logger.info(f"服务 {ss_port} 自动启动成功")
                        startup_message = "，服务已自动启动"
                    except Exception as db_error:
                        logger.error(f"更新服务状态失败: {db_error}")
                        startup_message = "，服务启动成功但状态更新失败"
                else:
                    logger.warning(f"服务 {ss_port} 自动启动失败: {stderr}")
                    startup_message = f"，但自动启动失败: {stderr}"
                    
            except Exception as start_error:
                logger.error(f"自动启动服务失败: {start_error}")
                startup_message = f"，但自动启动失败: {str(start_error)}"

            # 记录操作日志
            log_operation('add_service', f'port_{ss_port}',
                        f'添加服务成功 - SS端口: {ss_port}, 节点: {node_name}, SOCKS5: {socks_ip}:{socks_port}{startup_message}')

            flash(f'服务添加成功！Shadowsocks端口: {ss_port}，节点: {node_name}{startup_message}', 'success')
            return redirect(url_for('index'))

        except Exception as e:
            logger.error(f"添加服务失败: {e}")
            flash(f'添加服务失败: {str(e)}', 'error')
            return render_template('add_service.html')

    # GET请求，显示添加服务页面
    return render_template('add_service.html')

@app.route('/monitor')
@login_required
def monitor():
    """监控页"""
    try:
        services = get_services()
        system_stats = get_system_stats()
        return render_template('monitor.html', services=services, system_stats=system_stats)
    except Exception as e:
        logger.error(f"监控页加载失败: {e}")
        flash('加载监控页面失败', 'error')
        return render_template('monitor.html', services=[], system_stats={})

@app.route('/logs')
@login_required
def logs():
    """日志页"""
    return render_template('logs.html')

@app.route('/admin')
@admin_required
def admin_panel():
    """管理员面板"""
    try:
        db = get_db()

        # 获取用户统计
        users = db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()

        # 获取操作日志
        recent_logs = db.execute('''
            SELECT ol.*, u.username
            FROM operation_logs ol
            LEFT JOIN users u ON ol.user_id = u.id
            ORDER BY ol.timestamp DESC
            LIMIT 50
        ''').fetchall()

        # 获取系统设置
        settings = db.execute('SELECT * FROM system_settings ORDER BY key').fetchall()

        return render_template('admin.html',
                             users=users,
                             recent_logs=recent_logs,
                             settings=settings)
    except Exception as e:
        logger.error(f"管理员面板加载失败: {e}")
        flash('加载管理员面板失败', 'error')
        return redirect(url_for('index'))

# 错误处理
@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html',
                         error_code=404,
                         error_message='页面不存在'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html',
                         error_code=500,
                         error_message='服务器内部错误'), 500

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('error.html',
                         error_code=403,
                         error_message='权限不足'), 403

# 定时清理任务
def cleanup_old_data():
    """清理旧数据"""
    try:
        with app.app_context():
            db = get_db()

            # 清理30天前的监控数据
            db.execute('''
                DELETE FROM monitor_data
                WHERE timestamp < datetime('now', '-30 days')
            ''')

            # 清理90天前的操作日志
            db.execute('''
                DELETE FROM operation_logs
                WHERE timestamp < datetime('now', '-90 days')
            ''')

            db.commit()
            logger.info("旧数据清理完成")

    except Exception as e:
        logger.error(f"清理旧数据失败: {e}")



# 启动后台任务
def start_background_tasks():
    """启动后台任务"""
    def background_worker():
        while True:
            try:
                # 每小时清理一次旧数据
                cleanup_old_data()
                time.sleep(3600)  # 1小时
            except Exception as e:
                logger.error(f"后台任务异常: {e}")
                time.sleep(60)  # 出错后等待1分钟再重试

    # 启动后台线程
    background_thread = threading.Thread(target=background_worker, daemon=True)
    background_thread.start()
    logger.info("后台任务已启动")

if __name__ == '__main__':
    try:
        # 初始化数据库
        logger.info("正在初始化数据库...")
        init_db()

        # 启动后台任务
        logger.info("正在启动后台任务...")
        start_background_tasks()

        # 检查Xray脚本
        if not os.path.exists(XRAY_SCRIPT):
            logger.warning(f"Xray脚本不存在: {XRAY_SCRIPT}")
        else:
            logger.info(f"Xray脚本路径: {XRAY_SCRIPT}")

        logger.info("Web应用启动成功")
        logger.info("访问地址: http://localhost:9090")
        logger.info("默认用户: admin / admin123")

        # 启动应用
        app.run(
            debug=False,
            host='0.0.0.0',
            port=9090,
            threaded=True
        )

    except Exception as e:
        logger.error(f"应用启动失败: {e}")
        raise
