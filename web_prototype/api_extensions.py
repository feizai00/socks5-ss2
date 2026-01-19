#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API扩展模块 - 系统监控、回收站、备份恢复等功能
"""

import os
import json
import shutil
import sqlite3
import zipfile
from datetime import datetime, timedelta
from flask import jsonify, request
from system_monitor import monitor
import logging

logger = logging.getLogger(__name__)

def register_api_extensions(app, login_required, DB_PATH):
    """注册API扩展"""
    
    @app.route('/api/system/info')
    @login_required
    def api_system_info():
        """获取系统信息API"""
        try:
            # 获取真实系统信息
            system_info = monitor.get_all_info()
            
            # 简化返回格式以兼容前端
            simplified_info = {
                'cpu_usage': system_info['cpu'].get('usage', 0),
                'memory_usage': system_info['memory'].get('usage_percent', 0),
                'disk_usage': system_info['disk']['total'].get('usage_percent', 0),
                'network_in': system_info['network'].get('total_recv', 0),
                'network_out': system_info['network'].get('total_sent', 0),
                'uptime': system_info['processes']['uptime'].get('uptime_formatted', '未知'),
                'xray_processes': len(system_info.get('xray_services', [])),
                'total_processes': system_info['processes'].get('total_processes', 0),
                'load_avg': system_info['cpu'].get('load_avg', {}),
                'swap_usage': system_info['memory']['swap'].get('usage_percent', 0),
                'detailed': system_info  # 完整信息
            }
            
            return jsonify(simplified_info)
        except Exception as e:
            logger.error(f"获取系统信息失败: {e}")
            # 返回默认值以防止前端错误
            return jsonify({
                'cpu_usage': 0,
                'memory_usage': 0, 
                'disk_usage': 0,
                'network_in': 0,
                'network_out': 0,
                'uptime': '未知',
                'error': str(e)
            }), 500

    @app.route('/api/recycle')
    @login_required
    def api_recycle_list():
        """获取回收站列表"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # 查询已删除的服务
            cursor.execute('''
                SELECT port, node_name, deleted_at, created_by, created_at
                FROM services 
                WHERE deleted_at IS NOT NULL
                ORDER BY deleted_at DESC
            ''')
            
            services = []
            for row in cursor.fetchall():
                services.append({
                    'port': row[0],
                    'node_name': row[1],
                    'deleted_at': row[2],
                    'created_by': row[3],
                    'created_at': row[4]
                })
                
            conn.close()
            return jsonify({'services': services})
            
        except Exception as e:
            logger.error(f"获取回收站列表失败: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/recycle/<int:port>/restore', methods=['POST'])
    @login_required
    def api_restore_service(port):
        """从回收站恢复服务"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # 检查服务是否在回收站
            cursor.execute('SELECT * FROM services WHERE port = ? AND deleted_at IS NOT NULL', (port,))
            service = cursor.fetchone()
            
            if not service:
                return jsonify({'error': '服务不存在或未删除'}), 404
                
            # 恢复服务
            cursor.execute('UPDATE services SET deleted_at = NULL WHERE port = ?', (port,))
            
            # 移动配置文件从回收站
            recycle_path = os.path.join('data', '.recycle', str(port))
            service_path = os.path.join('data', 'services', str(port))
            
            if os.path.exists(recycle_path):
                shutil.move(recycle_path, service_path)
                
            conn.commit()
            conn.close()
            
            logger.info(f"服务 {port} 已从回收站恢复")
            return jsonify({'success': True, 'message': '服务恢复成功'})
            
        except Exception as e:
            logger.error(f"恢复服务失败: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/recycle/<int:port>', methods=['DELETE'])
    @login_required
    def api_permanent_delete_service(port):
        """永久删除回收站中的服务"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # 从数据库中永久删除
            cursor.execute('DELETE FROM services WHERE port = ? AND deleted_at IS NOT NULL', (port,))
            
            # 删除回收站中的文件
            recycle_path = os.path.join('data', '.recycle', str(port))
            if os.path.exists(recycle_path):
                shutil.rmtree(recycle_path)
                
            conn.commit()
            conn.close()
            
            logger.info(f"服务 {port} 已永久删除")
            return jsonify({'success': True, 'message': '服务永久删除成功'})
            
        except Exception as e:
            logger.error(f"永久删除服务失败: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/backup/create', methods=['POST'])
    @login_required
    def api_create_backup():
        """创建系统备份"""
        try:
            backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            backup_path = os.path.join('data', 'backups', backup_name)
            
            # 创建备份目录
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            
            # 创建ZIP文件
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # 备份数据库
                if os.path.exists(DB_PATH):
                    zipf.write(DB_PATH, 'database.db')
                
                # 备份服务配置
                services_dir = os.path.join('data', 'services')
                if os.path.exists(services_dir):
                    for root, dirs, files in os.walk(services_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, 'data')
                            zipf.write(file_path, arcname)
                
                # 备份系统配置
                config_files = ['xray_converter_simple.sh']
                for config_file in config_files:
                    if os.path.exists(config_file):
                        zipf.write(config_file, f'config/{config_file}')
            
            backup_info = {
                'name': backup_name,
                'path': backup_path,
                'size': os.path.getsize(backup_path),
                'created_at': datetime.now().isoformat()
            }
            
            logger.info(f"备份创建成功: {backup_name}")
            return jsonify({'success': True, 'backup': backup_info})
            
        except Exception as e:
            logger.error(f"创建备份失败: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/backup/list')
    @login_required
    def api_list_backups():
        """获取备份列表"""
        try:
            backup_dir = os.path.join('data', 'backups')
            backups = []
            
            if os.path.exists(backup_dir):
                for file in os.listdir(backup_dir):
                    if file.endswith('.zip'):
                        file_path = os.path.join(backup_dir, file)
                        stat = os.stat(file_path)
                        backups.append({
                            'name': file,
                            'size': stat.st_size,
                            'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat()
                        })
            
            # 按创建时间排序
            backups.sort(key=lambda x: x['created_at'], reverse=True)
            
            return jsonify({'backups': backups})
            
        except Exception as e:
            logger.error(f"获取备份列表失败: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/backup/<backup_name>/restore', methods=['POST'])
    @login_required
    def api_restore_backup(backup_name):
        """恢复备份"""
        try:
            backup_path = os.path.join('data', 'backups', backup_name)
            
            if not os.path.exists(backup_path):
                return jsonify({'error': '备份文件不存在'}), 404
            
            # 创建恢复前的备份
            pre_restore_backup = f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            pre_restore_path = os.path.join('data', 'backups', pre_restore_backup)
            
            with zipfile.ZipFile(pre_restore_path, 'w') as zipf:
                if os.path.exists(DB_PATH):
                    zipf.write(DB_PATH, 'database.db')
            
            # 解压备份文件
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                # 恢复数据库
                if 'database.db' in zipf.namelist():
                    zipf.extract('database.db', 'temp_restore')
                    shutil.move(os.path.join('temp_restore', 'database.db'), DB_PATH)
                
                # 恢复服务配置
                for file_info in zipf.infolist():
                    if file_info.filename.startswith('services/'):
                        zipf.extract(file_info, 'data')
            
            # 清理临时目录
            if os.path.exists('temp_restore'):
                shutil.rmtree('temp_restore')
            
            logger.info(f"备份恢复成功: {backup_name}")
            return jsonify({'success': True, 'message': '备份恢复成功'})
            
        except Exception as e:
            logger.error(f"恢复备份失败: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/recycle/cleanup', methods=['POST'])
    @login_required
    def api_cleanup_recycle():
        """清理超过30天的回收站项目"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # 查找超过30天的删除项目
            cutoff_date = datetime.now() - timedelta(days=30)
            cursor.execute('''
                SELECT port FROM services 
                WHERE deleted_at IS NOT NULL 
                AND deleted_at < ?
            ''', (cutoff_date.isoformat(),))
            
            expired_ports = [row[0] for row in cursor.fetchall()]
            
            # 永久删除过期项目
            for port in expired_ports:
                cursor.execute('DELETE FROM services WHERE port = ?', (port,))
                
                # 删除文件
                recycle_path = os.path.join('data', '.recycle', str(port))
                if os.path.exists(recycle_path):
                    shutil.rmtree(recycle_path)
            
            conn.commit()
            conn.close()
            
            logger.info(f"清理了 {len(expired_ports)} 个过期回收站项目")
            return jsonify({
                'success': True, 
                'cleaned_count': len(expired_ports),
                'message': f'清理了 {len(expired_ports)} 个过期项目'
            })
            
        except Exception as e:
            logger.error(f"清理回收站失败: {e}")
            return jsonify({'error': str(e)}), 500