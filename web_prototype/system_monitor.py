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
from database import get_db

class SystemMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.running = False

    def start(self):
        """启动监控 (占位符，如果需要后台线程监控可在此实现)"""
        self.running = True

    def stop(self):
        """停止监控"""
        self.running = False

    def get_system_status(self):
        """获取系统状态概览 (兼容 app.py 调用)"""
        return self.get_all_info()

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
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
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
            
            # 获取数据库连接 (如果可用)
            db = None
            try:
                db = get_db()
            except:
                pass

            if os.path.exists(data_dir):
                for port_dir in os.listdir(data_dir):
                    try:
                        port = int(port_dir)
                    except ValueError:
                        continue

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
                        port_listening = self._check_port_listening(port)
                        
                        # 获取连接数和流量
                        connection_count = 0
                        traffic_total = 0
                        
                        # 1. 获取数据库中的历史流量
                        if db:
                            row = db.execute("SELECT traffic_in, traffic_out FROM service_traffic WHERE service_port = ?", (port,)).fetchone()
                            if row:
                                traffic_total = row['traffic_in'] + row['traffic_out']
                        
                        # 2. 获取当前进程的实时流量 (如果有)
                        if pid and psutil.pid_exists(pid):
                            try:
                                proc = psutil.Process(pid)
                                # count established connections
                                connections = proc.connections()
                                connection_count = len(connections)
                                
                                # 累加当前进程的流量增量
                                io = proc.io_counters()
                                curr_read = io.read_bytes
                                curr_write = io.write_bytes
                                
                                # 计算相对于上一次保存点的增量
                                if port in self.traffic_cache and self.traffic_cache[port]['pid'] == pid:
                                    last = self.traffic_cache[port]
                                    delta_read = max(0, curr_read - last['read'])
                                    delta_write = max(0, curr_write - last['write'])
                                    traffic_total += (delta_read + delta_write)
                                else:
                                    # 如果没有缓存或者是新进程，直接加上当前值? 
                                    # 不，这样会重复计算。应该只加 delta。
                                    # 但为了实时显示，我们需要知道 "last saved" 的值。
                                    # 这里简化处理：直接显示 DB值 + 当前进程值？
                                    # 不行，因为 DB 值可能已经包含了当前进程的一部分。
                                    # 正确逻辑：traffic_total (显示值) = DB (已保存) + (Current - Last_Saved)
                                    # self.traffic_cache 存储的是 Last_Saved。
                                    
                                    # 如果缓存不存在，说明还没 save 过，或者刚启动。
                                    # 此时 Last_Saved 应该是 0 (对于新进程) 或者是 进程启动时的值?
                                    # 实际上，save_stats_to_db 会每分钟运行并更新 DB 和 traffic_cache。
                                    # 在两次 save 之间，traffic_cache 保持不变 (它是上一次 save 时的快照)。
                                    # 所以这里：
                                    if port in self.traffic_cache and self.traffic_cache[port]['pid'] == pid:
                                        last = self.traffic_cache[port]
                                        pending_read = max(0, curr_read - last['read'])
                                        pending_write = max(0, curr_write - last['write'])
                                        traffic_total += (pending_read + pending_write)
                                    else:
                                        # 如果没有缓存记录 (例如刚启动还没触发第一次 save)，
                                        # 我们暂时假设所有当前流量都是新增的 (但这可能会在重启 monitor 时导致重复显示，不过不影响 DB)
                                        # 或者更安全地，暂时不加 pending，等待第一次 save 后再显示实时增量。
                                        # 为了用户体验，我们加上当前值。
                                        traffic_total += (curr_read + curr_write)

                            except:
                                pass

                        # 获取节点名称
                        node_name = '未知'
                        if db:
                            svc = db.execute("SELECT node_name FROM services WHERE port = ?", (port,)).fetchone()
                            if svc:
                                node_name = svc['node_name']

                        services.append({
                            'port': port,
                            'node_name': node_name,
                            'status': status,
                            'pid': pid,
                            'port_listening': port_listening,
                            'log_exists': os.path.exists(log_file),
                            'connections': connection_count,
                            'traffic': self._format_bytes(traffic_total),  # 格式化流量
                            'traffic_raw': traffic_total
                        })
            
            return services
        except Exception as e:
            return {'error': str(e)}

    def _update_service_traffic(self, db):
        """更新服务流量统计 (持久化)"""
        try:
            data_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'services')
            if not os.path.exists(data_dir):
                return

            for port_dir in os.listdir(data_dir):
                try:
                    port = int(port_dir)
                    pid_file = os.path.join(data_dir, port_dir, 'xray.pid')
                    if os.path.exists(pid_file):
                        with open(pid_file, 'r') as f:
                            pid = int(f.read().strip())
                        
                        if psutil.pid_exists(pid):
                            proc = psutil.Process(pid)
                            io = proc.io_counters()
                            curr_read = io.read_bytes
                            curr_write = io.write_bytes
                            
                            delta_read = 0
                            delta_write = 0
                            
                            # 计算增量
                            if port in self.traffic_cache and self.traffic_cache[port]['pid'] == pid:
                                last = self.traffic_cache[port]
                                delta_read = max(0, curr_read - last['read'])
                                delta_write = max(0, curr_write - last['write'])
                            else:
                                # 新进程或首次运行，增量就是当前值
                                # 注意：如果是 monitor 重启但 xray 没重启，这里会导致重复计数吗？
                                # 是的。为了避免这种情况，我们需要知道 xray 进程已经运行了多久，或者 persist last_read in DB?
                                # 实际上，service_traffic 表只存总流量。
                                # 这种情况下，我们宁可少记不能多记? 或者只记录 delta?
                                # 如果是第一次发现这个 PID，我们应该假设之前的流量已经记入 DB 了吗？
                                # 这是一个难题。最稳妥的方法是：只记录 delta。
                                # 如果 self.traffic_cache 中没有这个 PID，我们将当前值作为基准 (baseline)，delta = 0。
                                # 这样会丢失 monitor 启动那一刻的 "current values"，但保证不会重复。
                                # 但如果 monitor 刚启动，curr_read 可能是 1GB。如果我们把这 1GB 算作 delta，那就重复了。
                                # 所以：如果 PID 变了或不在缓存中，Update cache but DO NOT update DB (delta=0).
                                delta_read = 0
                                delta_write = 0
                            
                            # 更新缓存
                            self.traffic_cache[port] = {
                                'pid': pid,
                                'read': curr_read,
                                'write': curr_write
                            }
                            
                            # 更新数据库
                            if delta_read > 0 or delta_write > 0:
                                # 检查记录是否存在
                                exists = db.execute("SELECT 1 FROM service_traffic WHERE service_port = ?", (port,)).fetchone()
                                if exists:
                                    db.execute('''
                                        UPDATE service_traffic 
                                        SET traffic_in = traffic_in + ?, traffic_out = traffic_out + ?, updated_at = CURRENT_TIMESTAMP
                                        WHERE service_port = ?
                                    ''', (delta_read, delta_write, port))
                                else:
                                    # 如果是新记录，我们是否应该把 curr_read 加上？
                                    # 不，根据上面的逻辑，我们只加 delta。
                                    # 但如果是全新服务，第一次 delta 是 0。
                                    # 这样会丢失第一分钟的流量。
                                    # 妥协：如果是 monitor 运行期间新创建的服务（我们可以通过 uptime 判断？），或者 database 中没有记录。
                                    # 如果 DB 中没有记录，说明是新服务，我们可以安全地插入 0 (等待下一次 delta)。
                                    db.execute('''
                                        INSERT INTO service_traffic (service_port, traffic_in, traffic_out)
                                        VALUES (?, 0, 0)
                                    ''', (port,))
                                    # 注意：这里我们插入 0，而不是 curr_read，以防重复。
                except:
                    pass
        except Exception as e:
            print(f"Error updating service traffic: {e}")

    def _update_system_traffic(self, db):
        """更新系统流量统计 (持久化)"""
        try:
            net_io = psutil.net_io_counters()
            curr_sent = net_io.bytes_sent
            curr_recv = net_io.bytes_recv
            
            delta_sent = 0
            delta_recv = 0
            
            if self.last_system_net_io:
                delta_sent = max(0, curr_sent - self.last_system_net_io['sent'])
                delta_recv = max(0, curr_recv - self.last_system_net_io['recv'])
            else:
                # 首次运行，初始化基准，不计算增量
                pass
                
            self.last_system_net_io = {'sent': curr_sent, 'recv': curr_recv}
            
            if delta_sent > 0 or delta_recv > 0:
                # 更新系统设置表中的总流量
                # 使用 INSERT OR IGNORE 初始化，然后 UPDATE
                db.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('total_network_in', '0')")
                db.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('total_network_out', '0')")
                
                db.execute("UPDATE system_settings SET value = CAST(value AS INTEGER) + ? WHERE key = 'total_network_in'", (delta_recv,))
                db.execute("UPDATE system_settings SET value = CAST(value AS INTEGER) + ? WHERE key = 'total_network_out'", (delta_sent,))
                
                # 同步回内存 offset，以便 get_network_info 能立即反映
                # 注意：get_network_info 是读取 DB 的，所以这里不需要手动加 self.system_traffic_offset
                # 但是为了性能，get_network_info 也可以读取内存。
                # 让我们在 get_network_info 里优先读 DB。
        except Exception as e:
            print(f"Error updating system traffic: {e}")

    def save_stats_to_db(self, app):
        """保存监控数据到数据库"""
        with app.app_context():
            try:
                db = get_db()
                
                # 更新流量统计 (持久化)
                self._update_service_traffic(db)
                self._update_system_traffic(db)
                
                # 1. 保存系统整体状态
                cpu_info = self.get_cpu_info()
                mem_info = self.get_memory_info()
                net_info = self.get_network_info()
                services = self.get_xray_services_status()
                
                total_connections = sum(s.get('connections', 0) for s in services if isinstance(s, dict))
                
                # 插入历史记录
                db.execute('''
                    INSERT INTO system_stats_history 
                    (cpu_usage, memory_usage, network_in, network_out, connections)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    cpu_info.get('usage', 0),
                    mem_info.get('usage_percent', 0),
                    net_info.get('bytes_recv', 0),
                    net_info.get('bytes_sent', 0),
                    total_connections
                ))
                
                # 2. 清理旧数据 (保留最近7天)
                db.execute("DELETE FROM system_stats_history WHERE timestamp < datetime('now', '-7 days')")
                
                db.commit()
                
            except Exception as e:
                # 在后台线程中打印错误可能看不到
                print(f"Monitor save stats error: {e}")

    
    def _check_port_listening(self, port):
        """检查端口是否在监听"""
        try:
            connections = psutil.net_connections()
            for conn in connections:
                if conn.laddr and len(conn.laddr) > 1 and conn.laddr[1] == port and conn.status == 'LISTEN':
                    return True
            return False
        except:
            return False
    
    def _bytes_to_gb(self, bytes_value):
        """将字节转换为GB"""
        return round(bytes_value / (1024**3), 2)
        
    def _format_bytes(self, size):
        """格式化字节显示"""
        power = 2**10
        n = 0
        power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        while size > power:
            size /= power
            n += 1
        return f"{size:.2f} {power_labels.get(n, 'P')}B"
    
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