#!/usr/bin/env python3
"""
Xray转换器Web管理系统 - 重构版
"""

import os
import logging
from flask import Flask, render_template, g
from config import Config
from database import init_db, close_db
from system_monitor import monitor
from routes.auth import auth_bp
from routes.main import main_bp
from routes.services import services_bp
from routes.api import api_bp
from api_extensions import register_api_extensions
from healer import ServiceHealer

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

from datetime import datetime

def create_app(test_config=None):
    # 创建 Flask 实例
    app = Flask(__name__, instance_relative_config=True)
    
    # 注入全局模板变量/函数
    @app.context_processor
    def inject_utilities():
        def moment(timestamp=None):
            if timestamp is None:
                return datetime.now()
            # 如果 timestamp 是 datetime 对象，直接返回
            if isinstance(timestamp, datetime):
                return timestamp
            try:
                return datetime.fromtimestamp(int(timestamp))
            except (ValueError, TypeError):
                # 如果转换失败，返回当前时间作为回退，避免崩溃
                return datetime.now()
        return dict(moment=moment)

    # 加载配置
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    
    # 确保配置生效
    Config.init_app(app)

    # 注册数据库关闭钩子
    app.teardown_appcontext(close_db)

    # 注册蓝图
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(services_bp)
    app.register_blueprint(api_bp)

    # 注册错误处理
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('error.html', error="页面未找到 (404)"), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('error.html', error="服务器内部错误 (500)"), 500

    # 启动系统监控
    monitor.start()
    
    # 启动历史数据记录线程
    import threading
    import time
    def history_recorder():
        while True:
            try:
                time.sleep(60) # 每分钟记录一次
                monitor.save_stats_to_db(app)
            except Exception as e:
                logger.error(f"历史数据记录异常: {e}")
                time.sleep(60)
                
    history_thread = threading.Thread(target=history_recorder)
    history_thread.daemon = True
    history_thread.start()
    
    # 启动自动故障修复监控
    healer = ServiceHealer(app)
    healer.start()

    # 初始化数据库
    with app.app_context():
        init_db(app)

    # 注册旧的 API 扩展 (兼容性)
    # 注意：这里需要传入一个假的 login_required，或者修改 api_extensions.py 以适应新结构
    # 暂时跳过复杂的修改，假设 login_required 在 routes.main 中定义
    from routes.main import login_required
    register_api_extensions(app, login_required, app.config['DB_PATH'])

    logger.info("应用启动成功")
    return app

if __name__ == '__main__':
    app = create_app()
    # 生产环境关闭 debug 模式，防止报错信息直接暴露，而是显示友好的 500 页面
    app.run(host='0.0.0.0', port=5000, debug=False)
