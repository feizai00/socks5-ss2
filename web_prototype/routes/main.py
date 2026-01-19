from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from functools import wraps
from database import get_db
from utils import log_operation
from system_monitor import monitor
import os

main_bp = Blueprint('main', __name__)

# 认证装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))

        db = get_db()
        user = db.execute(
            'SELECT role FROM users WHERE id = ?', (session['user_id'],)
        ).fetchone()

        if not user or user['role'] != 'admin':
            flash('需要管理员权限', 'error')
            return redirect(url_for('main.index'))

        return f(*args, **kwargs)
    return decorated_function

@main_bp.route('/')
@login_required
def index():
    """主页"""
    try:
        db = get_db()
        user_id = session['user_id']
        is_admin = session.get('role') == 'admin'

        # 获取统计信息
        if is_admin:
            # 管理员看到所有服务
            services = db.execute('SELECT * FROM services WHERE deleted_at IS NULL').fetchall()
            services = [dict(s) for s in services]
            total_users = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        else:
            # 普通用户只能看到自己的服务
            services = db.execute(
                'SELECT * FROM services WHERE created_by = ? AND deleted_at IS NULL',
                (user_id,)
            ).fetchall()
            services = [dict(s) for s in services]
            total_users = 0

        # 计算状态
        stats = {
            'total': len(services),
            'running': sum(1 for s in services if s['status'] == 'running'),
            'stopped': sum(1 for s in services if s['status'] == 'stopped'),
            'expired': sum(1 for s in services if s['status'] == 'expired')
        }

        # 获取最近操作日志
        if is_admin:
            logs = db.execute('''
                SELECT l.*, u.username 
                FROM operation_logs l
                LEFT JOIN users u ON l.user_id = u.id
                ORDER BY l.timestamp DESC LIMIT 10
            ''').fetchall()
        else:
            logs = db.execute('''
                SELECT l.*, u.username 
                FROM operation_logs l
                LEFT JOIN users u ON l.user_id = u.id
                WHERE l.user_id = ?
                ORDER BY l.timestamp DESC LIMIT 10
            ''', (user_id,)).fetchall()

        # 系统状态
        system_status = monitor.get_system_status()

        return render_template('index.html',
                             services=services,
                             stats=stats,
                             total_users=total_users,
                             logs=logs,
                             system_status=system_status,
                             is_admin=is_admin)
    except Exception as e:
        current_app.logger.error(f"加载主页失败: {e}")
        return render_template('error.html', error="加载数据失败"), 500

@main_bp.route('/admin')
@admin_required
def admin():
    """管理后台"""
    try:
        db = get_db()
        
        # 获取用户列表
        users = db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
        
        # 获取系统设置
        settings = db.execute('SELECT * FROM system_settings').fetchall()
        
        # 获取所有服务
        services = db.execute('''
            SELECT s.*, u.username 
            FROM services s
            LEFT JOIN users u ON s.created_by = u.id
            WHERE s.deleted_at IS NULL
            ORDER BY s.created_at DESC
        ''').fetchall()
        services = [dict(s) for s in services]
        
        return render_template('admin.html', 
                             users=users, 
                             settings=settings,
                             services=services)
    except Exception as e:
        current_app.logger.error(f"加载管理后台失败: {e}")
        flash('加载管理后台失败', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/logs')
@login_required
def view_logs():
    """查看日志"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page
    
    db = get_db()
    is_admin = session.get('role') == 'admin'
    user_id = session['user_id']
    
    query_parts = []
    params = []
    
    base_query = '''
        SELECT l.*, u.username 
        FROM operation_logs l
        LEFT JOIN users u ON l.user_id = u.id
    '''
    
    count_query = 'SELECT COUNT(*) FROM operation_logs l'
    
    if not is_admin:
        query_parts.append('l.user_id = ?')
        params.append(user_id)
        
    # 过滤条件
    action = request.args.get('action')
    if action:
        query_parts.append('l.action = ?')
        params.append(action)
        
    if query_parts:
        where_clause = ' WHERE ' + ' AND '.join(query_parts)
        base_query += where_clause
        count_query += where_clause
        
    # 排序和分页
    base_query += ' ORDER BY l.timestamp DESC LIMIT ? OFFSET ?'
    params.extend([per_page, offset])
    
    logs = db.execute(base_query, params).fetchall()
    
    # 获取总数以计算分页
    count_params = params[:-2]
    total_logs = db.execute(count_query, count_params).fetchone()[0]
    total_pages = (total_logs + per_page - 1) // per_page
    
    return render_template('logs.html', 
                         logs=logs, 
                         page=page, 
                         total_pages=total_pages,
                         current_action=action)

@main_bp.route('/monitor')
@login_required
def system_monitor_page():
    """系统监控页面"""
    return render_template('monitor.html')

@main_bp.route('/api/monitor/stats')
@login_required
def monitor_stats():
    """获取监控数据API"""
    try:
        status = monitor.get_system_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
