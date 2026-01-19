from flask import Blueprint, jsonify, request, session
from functools import wraps
from database import get_db
from utils import log_operation
from xray_manager import XrayManager

api_bp = Blueprint('api', __name__, url_prefix='/api')

# 认证装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function

@api_bp.route('/service/<int:service_id>/status')
@login_required
def get_service_status(service_id):
    """获取服务状态"""
    db = get_db()
    service = db.execute('SELECT port FROM services WHERE id = ?', (service_id,)).fetchone()
    
    if not service:
        return jsonify({'error': 'Service not found'}), 404
        
    is_running, _ = XrayManager.is_running(service['port'])
    status = 'running' if is_running else 'stopped'
    
    return jsonify({'status': status})

@api_bp.route('/service/<int:service_id>/logs')
@login_required
def get_service_logs(service_id):
    """获取服务日志"""
    db = get_db()
    service = db.execute('SELECT port FROM services WHERE id = ?', (service_id,)).fetchone()
    
    if not service:
        return jsonify({'error': 'Service not found'}), 404
        
    try:
        log_file = XrayManager.get_log_file(service['port'])
        with open(log_file, 'r') as f:
            lines = f.readlines()
            logs = lines[-100:] # 最后100行
        return jsonify({'logs': ''.join(logs)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
