from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from functools import wraps
from database import get_db
from utils import log_operation, SSLinkUtils  # 导入 SSLinkUtils
from system_monitor import monitor
import os

main_bp = Blueprint('main', __name__)
ss_utils = SSLinkUtils()  # 初始化

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

        # 为每个服务生成 SS 链接
        for s in services:
            s['ss_link'] = ss_utils.generate_ss_link(
                s['ss_password'],
                request.host.split(':')[0], # 获取当前访问的主机名/IP
                s['port'],
                s['node_name'],
                s['method']
            )

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

@main_bp.route('/servers')
@admin_required
def servers():
    """服务器管理页面"""
    try:
        db = get_db()
        servers = db.execute('SELECT * FROM servers ORDER BY created_at DESC').fetchall()
        return render_template('servers.html', servers=servers)
    except Exception as e:
        current_app.logger.error(f"加载服务器列表失败: {e}")
        flash('加载服务器列表失败', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/servers/add', methods=['POST'])
@admin_required
def add_server():
    """添加服务器"""
    try:
        name = request.form.get('name')
        ip = request.form.get('ip')
        domain = request.form.get('domain', '').strip()
        ssh_port = request.form.get('ssh_port', 22)
        username = request.form.get('username', 'root')
        password = request.form.get('password')
        
        if not name or not ip:
            flash('服务器名称和IP不能为空', 'error')
            return redirect(url_for('main.servers'))
            
        # 简单的连通性测试 (可选)
        # from ssh_manager import SSHManager
        # ssh = SSHManager(ip, int(ssh_port), username, password)
        # if not ssh.test_connection():
        #     flash('SSH 连接测试失败，请检查信息', 'warning')
        
        db = get_db()
        db.execute('''
            INSERT INTO servers (name, ip, domain, ssh_port, username, password)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, ip, domain, ssh_port, username, password))
        db.commit()
        
        # 如果配置了域名和Cloudflare，尝试自动添加DNS记录
        if domain:
            try:
                from cloudflare_manager import CloudflareManager
                settings = db.execute("SELECT key, value FROM system_settings WHERE key IN ('cf_api_token', 'cf_zone_id')").fetchall()
                settings_dict = {row['key']: row['value'] for row in settings}
                
                if settings_dict.get('cf_api_token') and settings_dict.get('cf_zone_id'):
                    cf = CloudflareManager(settings_dict['cf_api_token'], settings_dict['cf_zone_id'])
                    if cf.update_dns_record(domain, ip):
                        flash(f'服务器添加成功，且 DNS 记录已更新 ({domain} -> {ip})', 'success')
                    else:
                        flash('服务器添加成功，但 DNS 更新失败，请检查 Cloudflare 设置', 'warning')
                    return redirect(url_for('main.servers'))
            except Exception as e:
                current_app.logger.error(f"Cloudflare 操作失败: {e}")
        
        flash('服务器添加成功', 'success')
    except Exception as e:
        flash(f'添加失败: {e}', 'error')
        
    return redirect(url_for('main.servers'))

@main_bp.route('/servers/delete/<int:server_id>', methods=['POST'])
@admin_required
def delete_server(server_id):
    """删除服务器"""
    try:
        db = get_db()
        # 检查是否有服务正在使用该服务器
        count = db.execute('SELECT COUNT(*) FROM services WHERE server_id = ? AND deleted_at IS NULL', (server_id,)).fetchone()[0]
        if count > 0:
            return jsonify({'success': False, 'message': f'无法删除：该服务器上有 {count} 个活跃服务'}), 400
            
        db.execute('DELETE FROM servers WHERE id = ?', (server_id,))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@main_bp.route('/servers/update/<int:server_id>', methods=['POST'])
@admin_required
def update_server(server_id):
    """更新服务器信息"""
    try:
        name = request.form.get('name')
        ip = request.form.get('ip')
        domain = request.form.get('domain', '').strip()
        ssh_port = request.form.get('ssh_port')
        
        db = get_db()
        db.execute('''
            UPDATE servers 
            SET name = ?, ip = ?, domain = ?, ssh_port = ?, last_check = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (name, ip, domain, ssh_port, server_id))
        db.commit()
        
        # Cloudflare 同步
        if domain:
            try:
                from cloudflare_manager import CloudflareManager
                settings = db.execute("SELECT key, value FROM system_settings WHERE key IN ('cf_api_token', 'cf_zone_id')").fetchall()
                settings_dict = {row['key']: row['value'] for row in settings}
                
                if settings_dict.get('cf_api_token') and settings_dict.get('cf_zone_id'):
                    cf = CloudflareManager(settings_dict['cf_api_token'], settings_dict['cf_zone_id'])
                    cf.update_dns_record(domain, ip)
            except Exception as e:
                current_app.logger.error(f"Cloudflare 更新失败: {e}")
                
        flash('服务器信息已更新', 'success')
    except Exception as e:
        flash(f'更新失败: {e}', 'error')
    return redirect(url_for('main.servers'))

@main_bp.route('/servers/test/<int:server_id>', methods=['POST'])
@admin_required
def test_server(server_id):
    """测试服务器连接"""
    try:
        db = get_db()
        server = db.execute('SELECT * FROM servers WHERE id = ?', (server_id,)).fetchone()
        if not server:
            return jsonify({'success': False, 'message': '服务器不存在'}), 404
            
        from ssh_manager import SSHManager
        ssh = SSHManager(
            server['ip'], 
            server['ssh_port'], 
            server['username'], 
            server['password'], 
            server['private_key']
        )
        
        if ssh.test_connection():
            # 更新最后检查时间
            db.execute("UPDATE servers SET status = 'active', last_check = CURRENT_TIMESTAMP WHERE id = ?", (server_id,))
            db.commit()
            return jsonify({'success': True, 'message': '连接成功'})
        else:
            db.execute("UPDATE servers SET status = 'error', last_check = CURRENT_TIMESTAMP WHERE id = ?", (server_id,))
            db.commit()
            return jsonify({'success': False, 'message': '连接失败'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@main_bp.route('/ip-pool')
@admin_required
def ip_pool():
    """IP 备用池管理"""
    try:
        db = get_db()
        ips = db.execute('SELECT * FROM ip_pool ORDER BY created_at DESC').fetchall()
        return render_template('ip_pool.html', ips=ips)
    except Exception as e:
        current_app.logger.error(f"加载 IP 池失败: {e}")
        flash('加载 IP 池失败', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/ip-pool/add', methods=['POST'])
@admin_required
def add_ip():
    """添加 IP 到备用池"""
    try:
        data = request.form.get('ip_list', '').strip()
        if not data:
            flash('请输入 IP 信息', 'error')
            return redirect(url_for('main.ip_pool'))
        
        db = get_db()
        added_count = 0
        
        # 支持批量添加，一行一个
        lines = data.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 格式: ip:port:user:pass 或 ip:port
            parts = line.split(':')
            if len(parts) >= 2:
                socks_ip = parts[0]
                socks_port = int(parts[1])
                socks_user = parts[2] if len(parts) > 2 else None
                socks_pass = parts[3] if len(parts) > 3 else None
                
                db.execute('''
                    INSERT INTO ip_pool (socks_ip, socks_port, socks_user, socks_pass)
                    VALUES (?, ?, ?, ?)
                ''', (socks_ip, socks_port, socks_user, socks_pass))
                added_count += 1
        
        db.commit()
        flash(f'成功添加 {added_count} 个 IP', 'success')
    except Exception as e:
        flash(f'添加失败: {e}', 'error')
        
    return redirect(url_for('main.ip_pool'))

@main_bp.route('/ip-pool/delete/<int:ip_id>', methods=['POST'])
@admin_required
def delete_ip(ip_id):
    """删除备用 IP"""
    try:
        db = get_db()
        db.execute('DELETE FROM ip_pool WHERE id = ?', (ip_id,))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@main_bp.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    """系统设置"""
    db = get_db()
    if request.method == 'POST':
        try:
            for key, value in request.form.items():
                db.execute('''
                    INSERT INTO system_settings (key, value) 
                    VALUES (?, ?) 
                    ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP
                ''', (key, value, value))
            db.commit()
            flash('设置已更新', 'success')
            
            # 如果启用了自动修复，重启 healer (这里简化处理，实际上 healer 会读取最新配置)
            
        except Exception as e:
            flash(f'保存设置失败: {e}', 'error')
        return redirect(url_for('main.settings'))
        
    settings_rows = db.execute('SELECT * FROM system_settings').fetchall()
    settings = {row['key']: row['value'] for row in settings_rows}
    return render_template('settings.html', settings=settings)

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
    try:
        db = get_db()
        user_id = session['user_id']
        is_admin = session.get('role') == 'admin'

        if is_admin:
            services = db.execute('SELECT * FROM services WHERE deleted_at IS NULL').fetchall()
        else:
            services = db.execute(
                'SELECT * FROM services WHERE created_by = ? AND deleted_at IS NULL',
                (user_id,)
            ).fetchall()
        
        services = [dict(s) for s in services]
        
        return render_template('monitor.html', services=services)
    except Exception as e:
        current_app.logger.error(f"加载监控页面失败: {e}")
        return render_template('error.html', error="加载数据失败"), 500

@main_bp.route('/api/monitor/stats')
@login_required
def monitor_stats():
    """获取监控数据API"""
    try:
        status = monitor.get_system_status()
        
        # 补充历史数据用于前端图表
        db = get_db()
        history = db.execute('''
            SELECT cpu_usage, memory_usage, network_in, network_out, timestamp 
            FROM system_stats_history 
            ORDER BY timestamp DESC LIMIT 20
        ''').fetchall()
        
        # 将 row 对象转换为 dict 并反转顺序（按时间正序）
        status['history'] = [dict(row) for row in history][::-1]
        
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
