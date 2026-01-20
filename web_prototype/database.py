import sqlite3
import hashlib
import logging
from flask import g, current_app

logger = logging.getLogger(__name__)

def get_db():
    """获取数据库连接"""
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DB_PATH'])
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    """关闭数据库连接"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db(app):
    """初始化数据库"""
    with app.app_context():
        db_path = app.config['DB_PATH']
        conn = sqlite3.connect(db_path)
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
                deleted_at TIMESTAMP DEFAULT NULL,
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

        # 创建系统监控历史表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_stats_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cpu_usage REAL,
                memory_usage REAL,
                network_in INTEGER, -- 累计入站流量 (bytes)
                network_out INTEGER, -- 累计出站流量 (bytes)
                connections INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建服务流量统计表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS service_traffic (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_port INTEGER,
                traffic_in INTEGER DEFAULT 0, -- 累计入站流量 (bytes)
                traffic_out INTEGER DEFAULT 0, -- 累计出站流量 (bytes)
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (service_port) REFERENCES services (port)
            )
        ''')

        # 创建 IP 备用池表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ip_pool (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                socks_ip TEXT NOT NULL,
                socks_port INTEGER NOT NULL,
                socks_user TEXT,
                socks_pass TEXT,
                status TEXT DEFAULT 'available', -- available, used, bad
                last_checked_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

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
            ('tg_bot_token', '', 'Telegram 机器人 Token'),
            ('tg_chat_id', '', 'Telegram 通知 Chat ID'),
            ('auto_heal_enabled', 'false', '是否开启自动故障修复'),
        ]

        for key, value, desc in default_settings:
            cursor.execute('''
                INSERT OR IGNORE INTO system_settings (key, value, description)
                VALUES (?, ?, ?)
            ''', (key, value, desc))

        conn.commit()
        conn.close()
        logger.info("数据库初始化完成")
