from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from functools import wraps
from database import get_db
from utils import log_operation, validate_input, SSLinkUtils
from xray_manager import XrayManager
import random
import string
import secrets
import os
from config import Config

services_bp = Blueprint('services', __name__)
ss_utils = SSLinkUtils()

# 认证装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def check_service_permission(service_id):
    """检查用户是否有权访问该服务"""
    db = get_db()
    service = db.execute('SELECT * FROM services WHERE id = ?', (service_id,)).fetchone()
    
    if not service:
        return None, False
        
    if session.get('role') == 'admin':
        return dict(service), True
        
    if service['created_by'] == session['user_id']:
        return dict(service), True
        
    return dict(service), False

import time

@services_bp.route('/service/add', methods=['GET', 'POST'])
@login_required
def add_service():
    """添加新服务"""
    if request.method == 'POST':
        mode = request.form.get('mode', 'manual')
        
        # 公共数据
        data = {
            'port': str(random.randint(10000, 60000)),
            'ss_password': secrets.token_urlsafe(16),
            'method': request.form.get('method', 'aes-256-gcm'),
            'node_name': '',
            'socks_ip': '',
            'socks_port': '',
            'socks_user': '',
            'socks_pass': '',
            'expires_at': 0
        }
        
        try:
            if mode == 'quick':
                # 一键添加模式
                quick_input = request.form.get('quick_input', '').strip()
                parts = quick_input.split(':')
                
                if len(parts) < 6:
                    # 尝试兼容旧格式 (无有效期)
                    if len(parts) >= 5:
                        parts.append('0') # 默认为0
                    else:
                        raise ValueError("格式错误，应为: 节点名称:IP:端口:用户名:密码:有效期")
                
                # 检查 parts 是否为空字符串导致的解析错误
                if not parts[0].strip():
                     raise ValueError("格式错误: 节点名称不能为空")

                data['node_name'] = parts[0].strip()
                data['socks_ip'] = parts[1].strip()
                data['socks_port'] = parts[2].strip()
                data['socks_user'] = parts[3].strip()
                data['socks_pass'] = parts[4].strip()
                validity = parts[5].strip()
                
                # 计算有效期
                if validity in ['0', 'permanent', '永久']:
                    data['expires_at'] = 0
                elif validity.isdigit():
                    days = int(validity)
                    if days > 0:
                        data['expires_at'] = int(time.time()) + days * 86400
            else:
                # 手动模式
                data['node_name'] = request.form.get('node_name', '').strip()
                data['socks_ip'] = request.form.get('socks_ip', '').strip()
                data['socks_port'] = request.form.get('socks_port', '').strip()
                data['socks_user'] = request.form.get('socks_user', '').strip()
                data['socks_pass'] = request.form.get('socks_pass', '').strip()
                
                # 计算有效期
                expiry_type = request.form.get('expiry_type')
                custom_days = request.form.get('custom_days')
                
                days = 0
                if expiry_type == '7days':
                    days = 7
                elif expiry_type == '30days':
                    days = 30
                elif expiry_type == '90days':
                    days = 90
                elif expiry_type == 'custom' and custom_days and custom_days.isdigit():
                    days = int(custom_days)
                    
                if days > 0:
                    data['expires_at'] = int(time.time()) + days * 86400

            # 验证输入
            if not data['node_name']:
                raise ValueError("节点名称不能为空")
            if not data['socks_ip']:
                raise ValueError("代理IP不能为空")
            if not data['socks_port']:
                raise ValueError("代理端口不能为空")
            
            # 检查端口是否已使用
            db = get_db()
            
            # 检查节点名称是否重复 (新增)
            existing_name = db.execute(
                'SELECT id FROM services WHERE node_name = ? AND deleted_at IS NULL',
                (data['node_name'],)
            ).fetchone()
            if existing_name:
                raise ValueError(f"节点名称 '{data['node_name']}' 已存在，请使用其他名称")
            
            while True:
                existing = db.execute(
                    'SELECT id FROM services WHERE port = ? AND deleted_at IS NULL', 
                    (data['port'],)
                ).fetchone()
                if not existing:
                    break
                data['port'] = str(random.randint(10000, 60000))

            # 保存到数据库
            cursor = db.execute('''
                INSERT INTO services (
                    port, node_name, socks_ip, socks_port, socks_user, socks_pass,
                    ss_password, method, status, created_by, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['port'], data['node_name'], data['socks_ip'], data['socks_port'],
                data['socks_user'], data['socks_pass'], data['ss_password'], 
                data['method'], 'stopped', session['user_id'], data['expires_at']
            ))
            db.commit()
            service_id = cursor.lastrowid
            
            # 自动启动服务
            try:
                XrayManager.start_service(int(data['port']), data)
                
                # 更新状态
                db.execute(
                    'UPDATE services SET status = ? WHERE id = ?',
                    ('running', service_id)
                )
                db.commit()
                
                flash(f"服务 {data['node_name']} 创建并启动成功", 'success')
            except Exception as e:
                current_app.logger.error(f"启动服务失败: {e}")
                flash(f"服务创建成功但启动失败: {e}", 'warning')
            
            log_operation('create_service', data['node_name'], f"创建服务 端口:{data['port']}")
            
            # 生成SS链接并存入flash消息，以便在重定向后使用（可选，目前直接重定向到列表）
            # 或者重定向到详情页，这样用户可以直接看到生成的链接
            return redirect(url_for('services.service_detail', service_id=service_id))
            
        except ValueError as e:
            flash(str(e), 'error')
            return render_template('add_service.html', data=data)
        except Exception as e:
            current_app.logger.error(f"创建服务失败: {e}")
            flash(f"创建服务失败: {e}", 'error')
            return render_template('add_service.html', data=data)

    # 生成默认值
    default_data = {
        'port': random.randint(10000, 60000),
        'ss_password': secrets.token_urlsafe(16),
        'method': 'aes-256-gcm'
    }
    
    return render_template('add_service.html', data=default_data)

@services_bp.route('/service/<int:service_id>')
@login_required
def service_detail(service_id):
    """服务详情"""
    service, allowed = check_service_permission(service_id)
    
    if not service:
        flash('服务不存在', 'error')
        return redirect(url_for('main.index'))
        
    if not allowed:
        flash('无权访问该服务', 'error')
        return redirect(url_for('main.index'))
    
    # 获取运行状态
    is_running, pid = XrayManager.is_running(service['port'])
    
    # 如果数据库状态不一致，更新数据库
    db_status = service['status']
    actual_status = 'running' if is_running else 'stopped'
    
    if db_status != actual_status:
        db = get_db()
        db.execute('UPDATE services SET status = ? WHERE id = ?', (actual_status, service_id))
        db.commit()
        service = dict(service)
        service['status'] = actual_status
    
    # 生成SS链接
    ss_link = ss_utils.generate_ss_link(
        service['ss_password'],
        request.host.split(':')[0], # 获取当前访问的主机名/IP
        service['port'],
        service['node_name'],
        service['method']
    )
    
    # 读取日志
    logs = []
    log_file = XrayManager.get_log_file(service['port'])
    if os.path.exists(log_file):
        try:
            # 读取最后 100 行
            with open(log_file, 'r') as f:
                lines = f.readlines()
                logs = lines[-100:]
        except Exception as e:
            current_app.logger.error(f"读取日志失败: {e}")
            logs = [f"读取日志失败: {e}"]
            
    return render_template('service_detail.html', 
                         service=service, 
                         ss_link=ss_link,
                         logs=''.join(logs))

@services_bp.route('/service/<int:service_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_service(service_id):
    """编辑服务"""
    service, allowed = check_service_permission(service_id)
    
    if not service or not allowed:
        flash('无法访问该服务', 'error')
        return redirect(url_for('main.index'))
        
    if request.method == 'POST':
        # 获取表单数据
        data = {
            'node_name': request.form.get('node_name', '').strip(),
            'socks_ip': request.form.get('socks_ip', '').strip(),
            'socks_port': request.form.get('socks_port', '').strip(),
            'socks_user': request.form.get('socks_user', '').strip(),
            'socks_pass': request.form.get('socks_pass', '').strip(),
            'ss_password': request.form.get('ss_password', '').strip(),
            'method': request.form.get('method', 'aes-256-gcm')
        }
        
        # 验证...
        # 这里简化验证逻辑，实际上应该和add_service一样严格
        
        try:
            db = get_db()
            db.execute('''
                UPDATE services SET
                    node_name = ?, socks_ip = ?, socks_port = ?,
                    socks_user = ?, socks_pass = ?, ss_password = ?,
                    method = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (
                data['node_name'], data['socks_ip'], data['socks_port'],
                data['socks_user'], data['socks_pass'], data['ss_password'],
                data['method'], service_id
            ))
            db.commit()
            
            # 如果服务正在运行，需要重启以应用更改
            # 构造完整的服务数据以供重启使用
            service_data = dict(service)
            service_data.update(data)
            
            if service['status'] == 'running':
                XrayManager.restart_service(service['port'], service_data)
                flash('服务配置已更新并重启', 'success')
            else:
                # 即使没运行，也重新生成配置文件
                XrayManager.generate_config(service_data)
                flash('服务配置已更新', 'success')
                
            log_operation('edit_service', data['node_name'], f"更新服务 ID:{service_id}")
            return redirect(url_for('services.service_detail', service_id=service_id))
            
        except Exception as e:
            current_app.logger.error(f"更新服务失败: {e}")
            flash(f"更新服务失败: {e}", 'error')
            
    return render_template('edit_service.html', service=service)

@services_bp.route('/service/<int:service_id>/start')
@login_required
def start_service_route(service_id):
    """启动服务"""
    service, allowed = check_service_permission(service_id)
    if not service or not allowed:
        return jsonify({'error': '无权访问'}), 403
        
    try:
        XrayManager.start_service(service['port'], dict(service))
        
        db = get_db()
        db.execute('UPDATE services SET status = ? WHERE id = ?', ('running', service_id))
        db.commit()
        
        log_operation('start_service', service['node_name'], f"启动服务 端口:{service['port']}")
        flash('服务已启动', 'success')
    except Exception as e:
        current_app.logger.error(f"启动服务失败: {e}")
        flash(f"启动服务失败: {e}", 'error')
        
    return redirect(request.referrer or url_for('main.index'))

@services_bp.route('/service/<int:service_id>/stop')
@login_required
def stop_service_route(service_id):
    """停止服务"""
    service, allowed = check_service_permission(service_id)
    if not service or not allowed:
        return jsonify({'error': '无权访问'}), 403
        
    try:
        XrayManager.stop_service(service['port'])
        
        db = get_db()
        db.execute('UPDATE services SET status = ? WHERE id = ?', ('stopped', service_id))
        db.commit()
        
        log_operation('stop_service', service['node_name'], f"停止服务 端口:{service['port']}")
        flash('服务已停止', 'success')
    except Exception as e:
        current_app.logger.error(f"停止服务失败: {e}")
        flash(f"停止服务失败: {e}", 'error')
        
    return redirect(request.referrer or url_for('main.index'))

@services_bp.route('/service/<int:service_id>/restart')
@login_required
def restart_service_route(service_id):
    """重启服务"""
    service, allowed = check_service_permission(service_id)
    if not service or not allowed:
        return jsonify({'error': '无权访问'}), 403
        
    try:
        XrayManager.restart_service(service['port'], dict(service))
        
        db = get_db()
        db.execute('UPDATE services SET status = ? WHERE id = ?', ('running', service_id))
        db.commit()
        
        log_operation('restart_service', service['node_name'], f"重启服务 端口:{service['port']}")
        flash('服务已重启', 'success')
    except Exception as e:
        current_app.logger.error(f"重启服务失败: {e}")
        flash(f"重启服务失败: {e}", 'error')
        
    return redirect(request.referrer or url_for('main.index'))

@services_bp.route('/service/<int:service_id>/delete', methods=['POST'])
@login_required
def delete_service(service_id):
    """删除服务"""
    service, allowed = check_service_permission(service_id)
    if not service or not allowed:
        return jsonify({'error': '无权访问'}), 403
        
    try:
        # 停止服务
        XrayManager.stop_service(service['port'])
        
        # 软删除
        db = get_db()
        db.execute('''
            UPDATE services 
            SET deleted_at = CURRENT_TIMESTAMP, status = 'stopped' 
            WHERE id = ?
        ''', (service_id,))
        db.commit()
        
        log_operation('delete_service', service['node_name'], f"删除服务 端口:{service['port']}")
        flash('服务已删除', 'success')
    except Exception as e:
        current_app.logger.error(f"删除服务失败: {e}")
        flash(f"删除服务失败: {e}", 'error')
        
    return redirect(url_for('main.index'))
