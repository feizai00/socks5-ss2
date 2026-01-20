from flask import Blueprint, jsonify, request, session, current_app
from functools import wraps
from database import get_db
from utils import log_operation, SSLinkUtils
from xray_manager import XrayManager

api_bp = Blueprint('api', __name__, url_prefix='/api')
ss_utils = SSLinkUtils()

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

@api_bp.route('/services/<port>/test-ss', methods=['POST'])
@login_required
def test_ss_link(port):
    """测试SS链接 (检查本地端口是否监听)"""
    try:
        port = int(port)
        # 测试本地端口连通性
        # 使用 127.0.0.1 测试本地服务是否正常启动
        latency = ss_utils.test_connection('127.0.0.1', port)
        
        if latency >= 0:
            return jsonify({'success': True, 'latency': latency, 'message': '服务正常'})
        else:
            return jsonify({'success': False, 'message': '端口无法连接'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/test-ss-batch', methods=['POST'])
@login_required
def batch_test_ss_link():
    """批量测试SS链接"""
    data = request.get_json()
    ports = data.get('ports', [])
    
    db = get_db()
    results = []
    success_count = 0
    
    for port in ports:
        try:
            port_int = int(port)
            # 获取服务信息
            service = db.execute(
                'SELECT node_name, socks_ip, socks_port FROM services WHERE port = ?',
                (str(port_int),)
            ).fetchone()
            
            node_name = service['node_name'] if service else '未知服务'
            server_ip = '127.0.0.1' # 测试的是本地服务
            
            latency = ss_utils.test_connection(server_ip, port_int)
            
            result_item = {
                'port': port_int,
                'node_name': node_name,
                'server': request.host.split(':')[0], # 返回给前端显示的服务器地址
                'server_port': port_int,
                'success': latency >= 0,
                'latency': latency,
                'message': '连接成功' if latency >= 0 else '无法连接'
            }
            
            if latency >= 0:
                success_count += 1
                
            results.append(result_item)
            
        except Exception as e:
            results.append({
                'port': port,
                'node_name': '未知',
                'server': 'unknown',
                'server_port': port,
                'success': False,
                'latency': -1,
                'message': f'错误: {str(e)}'
            })
            
    return jsonify({
        'success': True,
        'summary': {
            'total': len(ports),
            'success': success_count
        },
        'results': results
    })


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
