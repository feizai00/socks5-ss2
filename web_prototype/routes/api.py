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

@api_bp.route('/services/<port>', methods=['DELETE'])
@login_required
def delete_service_by_port(port):
    """通过端口删除服务 (用于前端 API 调用)"""
    db = get_db()
    
    # 查找服务 ID
    service = db.execute(
        'SELECT id, node_name, created_by FROM services WHERE port = ? AND deleted_at IS NULL', 
        (port,)
    ).fetchone()
    
    if not service:
        return jsonify({'error': '服务不存在'}), 404
        
    # 权限检查
    if session.get('role') != 'admin' and service['created_by'] != session['user_id']:
        return jsonify({'error': '无权操作'}), 403
        
    try:
        # 停止服务
        XrayManager.stop_service(port)
        
        # 软删除
        db.execute('''
            UPDATE services 
            SET deleted_at = CURRENT_TIMESTAMP, status = 'stopped' 
            WHERE id = ?
        ''', (service['id'],))
        db.commit()
        
        log_operation('delete_service', service['node_name'], f"删除服务 端口:{port}")
        return jsonify({'success': True, 'message': '服务已删除'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
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
