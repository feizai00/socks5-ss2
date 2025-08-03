#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统监控模块 - 获取真实的系统信息
"""

import os
import psutil
import time
import json
import subprocess
from datetime import datetime, timedelta

class SystemMonitor:
    def __init__(self):
        self.start_time = time.time()
    
    def get_cpu_info(self):
        """获取CPU信息"""
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # CPU核心数
            cpu_count = psutil.cpu_count()
            cpu_count_logical = psutil.cpu_count(logical=True)
            
            # CPU频率
            cpu_freq = psutil.cpu_freq()
            
            # 负载平均值 (Linux/macOS)
            try:
                load_avg = os.getloadavg()
            except:
                load_avg = [0, 0, 0]
            
            return {
                'usage': round(cpu_percent, 1),
                'cores_physical': cpu_count,
                'cores_logical': cpu_count_logical,
                'frequency': {
                    'current': round(cpu_freq.current, 1) if cpu_freq else 0,
                    'min': round(cpu_freq.min, 1) if cpu_freq else 0,
                    'max': round(cpu_freq.max, 1) if cpu_freq else 0
                },
                'load_avg': {
                    '1min': round(load_avg[0], 2),
                    '5min': round(load_avg[1], 2),
                    '15min': round(load_avg[2], 2)
                }
            }
        except Exception as e:
            return {'error': str(e), 'usage': 0}
    
    def get_memory_info(self):
        """获取内存信息"""
        try:
            # 系统内存
            memory = psutil.virtual_memory()
            
            # 交换分区
            swap = psutil.swap_memory()
            
            return {
                'total': self._bytes_to_gb(memory.total),
                'available': self._bytes_to_gb(memory.available),
                'used': self._bytes_to_gb(memory.used),
                'usage_percent': round(memory.percent, 1),
                'free': self._bytes_to_gb(memory.free),
                'swap': {
                    'total': self._bytes_to_gb(swap.total),
                    'used': self._bytes_to_gb(swap.used),
                    'free': self._bytes_to_gb(swap.free),
                    'usage_percent': round(swap.percent, 1) if swap.total > 0 else 0
                }
            }
        except Exception as e:
            return {'error': str(e), 'usage_percent': 0}
    
    def get_disk_info(self):
        """获取磁盘信息"""
        try:
            # 获取所有磁盘分区
            partitions = psutil.disk_partitions()
            disk_info = []
            
            total_size = 0
            total_used = 0
            total_free = 0
            
            for partition in partitions:
                try:
                    partition_usage = psutil.disk_usage(partition.mountpoint)
                    
                    size_gb = self._bytes_to_gb(partition_usage.total)
                    used_gb = self._bytes_to_gb(partition_usage.used)
                    free_gb = self._bytes_to_gb(partition_usage.free)
                    
                    disk_info.append({
                        'device': partition.device,
                        'mountpoint': partition.mountpoint,
                        'fstype': partition.fstype,
                        'total': size_gb,
                        'used': used_gb,
                        'free': free_gb,
                        'usage_percent': round((partition_usage.used / partition_usage.total) * 100, 1)
                    })
                    
                    total_size += size_gb
                    total_used += used_gb
                    total_free += free_gb
                    
                except PermissionError:
                    continue
            
            # 磁盘I/O统计
            disk_io = psutil.disk_io_counters()
            
            return {
                'partitions': disk_info,
                'total': {
                    'size': round(total_size, 1),
                    'used': round(total_used, 1),
                    'free': round(total_free, 1),
                    'usage_percent': round((total_used / total_size) * 100, 1) if total_size > 0 else 0
                },
                'io': {
                    'read_bytes': self._bytes_to_gb(disk_io.read_bytes) if disk_io else 0,
                    'write_bytes': self._bytes_to_gb(disk_io.write_bytes) if disk_io else 0,
                    'read_count': disk_io.read_count if disk_io else 0,
                    'write_count': disk_io.write_count if disk_io else 0
                }
            }
        except Exception as e:
            return {'error': str(e), 'total': {'usage_percent': 0}}
    
    def get_network_info(self):
        """获取网络信息"""
        try:
            # 网络I/O统计
            net_io = psutil.net_io_counters()
            
            # 网络接口信息
            interfaces = []
            net_if_addrs = psutil.net_if_addrs()
            net_if_stats = psutil.net_if_stats()
            
            for interface_name, addresses in net_if_addrs.items():
                if interface_name in net_if_stats:
                    stats = net_if_stats[interface_name]
                    
                    # 获取IP地址
                    ipv4_addr = None
                    ipv6_addr = None
                    
                    for addr in addresses:
                        if addr.family == 2:  # IPv4
                            ipv4_addr = addr.address
                        elif addr.family == 10:  # IPv6
                            ipv6_addr = addr.address
                    
                    interfaces.append({
                        'name': interface_name,
                        'ipv4': ipv4_addr,
                        'ipv6': ipv6_addr,
                        'is_up': stats.isup,
                        'speed': stats.speed,
                        'mtu': stats.mtu
                    })
            
            return {
                'total_sent': self._bytes_to_gb(net_io.bytes_sent),
                'total_recv': self._bytes_to_gb(net_io.bytes_recv),
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv,
                'interfaces': interfaces
            }
        except Exception as e:
            return {'error': str(e)}
    
    def get_process_info(self):
        """获取进程信息"""
        try:
            # 总进程数
            process_count = len(psutil.pids())
            
            # Xray相关进程
            xray_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'cmdline']):
                try:
                    if 'xray' in proc.info['name'].lower() or \
                       (proc.info['cmdline'] and any('xray' in cmd.lower() for cmd in proc.info['cmdline'])):
                        xray_processes.append({
                            'pid': proc.info['pid'],
                            'name': proc.info['name'],
                            'cpu_percent': round(proc.info['cpu_percent'], 1),
                            'memory_percent': round(proc.info['memory_percent'], 1),
                            'cmdline': ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # 系统启动时间
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot_time
            
            return {
                'total_processes': process_count,
                'xray_processes': xray_processes,
                'uptime': {
                    'boot_time': boot_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'uptime_seconds': int(uptime.total_seconds()),
                    'uptime_formatted': str(uptime).split('.')[0]
                }
            }
        except Exception as e:
            return {'error': str(e), 'total_processes': 0}
    
    def get_system_info(self):
        """获取系统基本信息"""
        try:
            import platform
            
            # 系统信息
            uname = platform.uname()
            
            # Python版本
            python_version = platform.python_version()
            
            return {
                'system': uname.system,
                'node': uname.node,
                'release': uname.release,
                'version': uname.version,
                'machine': uname.machine,
                'processor': uname.processor,
                'python_version': python_version,
                'architecture': platform.architecture()[0]
            }
        except Exception as e:
            return {'error': str(e)}
    
    def get_xray_services_status(self):
        """获取Xray服务状态"""
        try:
            services = []
            data_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'services')
            
            if os.path.exists(data_dir):
                for port_dir in os.listdir(data_dir):
                    port_path = os.path.join(data_dir, port_dir)
                    if os.path.isdir(port_path):
                        pid_file = os.path.join(port_path, 'xray.pid')
                        log_file = os.path.join(port_path, 'xray.log')
                        
                        status = 'stopped'
                        pid = None
                        
                        # 检查PID文件
                        if os.path.exists(pid_file):
                            try:
                                with open(pid_file, 'r') as f:
                                    pid = int(f.read().strip())
                                
                                # 检查进程是否存在
                                if psutil.pid_exists(pid):
                                    try:
                                        proc = psutil.Process(pid)
                                        if proc.is_running():
                                            status = 'running'
                                    except:
                                        status = 'error'
                            except:
                                pass
                        
                        # 检查端口监听
                        port_listening = self._check_port_listening(int(port_dir))
                        
                        services.append({
                            'port': int(port_dir),
                            'status': status,
                            'pid': pid,
                            'port_listening': port_listening,
                            'log_exists': os.path.exists(log_file)
                        })
            
            return services
        except Exception as e:
            return {'error': str(e)}
    
    def _check_port_listening(self, port):
        """检查端口是否在监听"""
        try:
            connections = psutil.net_connections()
            for conn in connections:
                if conn.laddr.port == port and conn.status == 'LISTEN':
                    return True
            return False
        except:
            return False
    
    def _bytes_to_gb(self, bytes_value):
        """将字节转换为GB"""
        return round(bytes_value / (1024**3), 2)
    
    def get_all_info(self):
        """获取所有系统信息"""
        return {
            'timestamp': datetime.now().isoformat(),
            'system': self.get_system_info(),
            'cpu': self.get_cpu_info(),
            'memory': self.get_memory_info(),
            'disk': self.get_disk_info(),
            'network': self.get_network_info(),
            'processes': self.get_process_info(),
            'xray_services': self.get_xray_services_status()
        }

# 创建全局实例
monitor = SystemMonitor()

if __name__ == "__main__":
    # 测试输出
    info = monitor.get_all_info()
    print(json.dumps(info, indent=2, ensure_ascii=False))