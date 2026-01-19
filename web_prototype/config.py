import os
from datetime import timedelta

class Config:
    # 基础路径配置
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    PARENT_DIR = os.path.dirname(BASE_DIR)
    
    # 数据和脚本路径
    # 优先检查根目录下的 xray，兼容旧结构 (xray/xray)
    if os.path.isfile(os.path.join(PARENT_DIR, 'xray')):
        XRAY_BIN_PATH = os.path.join(PARENT_DIR, 'xray')
    else:
        XRAY_BIN_PATH = os.path.join(PARENT_DIR, 'xray', 'xray')
        
    GEOIP_PATH = os.path.join(PARENT_DIR, 'geoip.dat')
    GEOSITE_PATH = os.path.join(PARENT_DIR, 'geosite.dat')
    
    # 数据存储
    DATA_DIR = os.path.join(PARENT_DIR, 'data')
    SERVICE_DIR = os.path.join(DATA_DIR, 'services')
    DB_PATH = os.environ.get('DB_PATH') or os.path.join(BASE_DIR, 'xray_web.db')
    
    # 上传文件
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # 安全配置
    # 优先从环境变量获取密钥，否则使用默认值（生产环境应强制设置环境变量）
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-please-change-in-prod'
    SESSION_COOKIE_SECURE = False  # 生产环境建议设为 True (配合 HTTPS)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)

    # 确保必要目录存在
    @staticmethod
    def init_app(app):
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(os.path.dirname(Config.DB_PATH), exist_ok=True)
        os.makedirs(os.path.join(Config.DATA_DIR, '.recycle'), exist_ok=True)
        os.makedirs(os.path.join(Config.DATA_DIR, 'backups'), exist_ok=True)
