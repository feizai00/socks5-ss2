import os
import json
import subprocess
import psutil
import logging
import signal
from config import Config

logger = logging.getLogger(__name__)

class XrayManager:
    @staticmethod
    def generate_config(service_data):
        """生成 Xray 配置字典"""
        port = service_data['port']
        password = service_data['ss_password']
        method = service_data.get('method', 'aes-256-gcm')
        socks_ip = service_data['socks_ip']
        socks_port = service_data['socks_port']
        socks_user = service_data.get('socks_user')
        socks_pass = service_data.get('socks_pass')

        config = {
            "log": {
                "loglevel": "warning",
                "access": "",
                "error": ""
            },
            "inbounds": [
                {
                    "port": port,
                    "protocol": "shadowsocks",
                    "settings": {
                        "method": method,
                        "password": password,
                        "network": "tcp,udp"
                    },
                    "streamSettings": {
                        "sockopt": {
                            "tcpKeepAlive": True,
                            "tcpNoDelay": True
                        }
                    }
                }
            ],
            "outbounds": [
                {
                    "protocol": "socks",
                    "settings": {
                        "servers": [
                            {
                                "address": socks_ip,
                                "port": int(socks_port),
                                "users": [{"user": socks_user, "pass": socks_pass}] if socks_user and socks_pass else []
                            }
                        ]
                    },
                    "streamSettings": {
                        "sockopt": {
                            "tcpKeepAlive": True,
                            "tcpNoDelay": True
                        }
                    }
                },
                {
                    "protocol": "freedom",
                    "tag": "direct"
                }
            ],
            "routing": {
                "rules": [
                    {
                        "type": "field",
                        "outboundTag": "direct",
                        "domain": ["localhost", "127.0.0.1"]
                    }
                ]
            }
        }
        return config

    @staticmethod
    def save_config(port, config):
        """保存配置文件"""
        service_dir = os.path.join(Config.SERVICE_DIR, str(port))
        os.makedirs(service_dir, exist_ok=True)
        config_path = os.path.join(service_dir, 'config.json')
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return config_path

    @staticmethod
    def get_pid_file(port):
        return os.path.join(Config.SERVICE_DIR, str(port), 'xray.pid')

    @staticmethod
    def get_log_file(port):
        return os.path.join(Config.SERVICE_DIR, str(port), 'xray.log')

    @staticmethod
    def is_running(port):
        """检查服务是否运行"""
        pid_file = XrayManager.get_pid_file(port)
        if not os.path.exists(pid_file):
            return False, None
        
        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            if psutil.pid_exists(pid):
                try:
                    process = psutil.Process(pid)
                    if process.status() != psutil.STATUS_ZOMBIE:
                        return True, pid
                except psutil.NoSuchProcess:
                    pass
            
            # 如果 PID 文件存在但进程不存在，清理 PID 文件
            os.remove(pid_file)
            return False, None
        except (ValueError, IOError):
            return False, None

    @staticmethod
    def start_service(port, service_data=None):
        """启动服务"""
        # 如果提供了数据，先生成配置
        if service_data:
            config = XrayManager.generate_config(service_data)
            XrayManager.save_config(port, config)
        
        config_path = os.path.join(Config.SERVICE_DIR, str(port), 'config.json')
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found for port {port}")

        running, _ = XrayManager.is_running(port)
        if running:
            return True

        # 检查端口占用
        for conn in psutil.net_connections():
            if conn.laddr and len(conn.laddr) > 1 and conn.laddr[1] == port:
                 # 如果是被占用了，抛出异常
                raise OSError(f"Port {port} is already in use")

        log_file = XrayManager.get_log_file(port)
        pid_file = XrayManager.get_pid_file(port)

        # 轮换日志
        if os.path.exists(log_file) and os.path.getsize(log_file) > 10 * 1024 * 1024:
            os.rename(log_file, log_file + '.old')

        # 确保 xray 可执行
        if not os.access(Config.XRAY_BIN_PATH, os.X_OK):
             os.chmod(Config.XRAY_BIN_PATH, 0o755)

        with open(log_file, 'a') as log_f:
            process = subprocess.Popen(
                [Config.XRAY_BIN_PATH, 'run', '-config', config_path],
                stdout=log_f,
                stderr=log_f,
                start_new_session=True  # 类似于 setsid
            )
        
        with open(pid_file, 'w') as f:
            f.write(str(process.pid))
            
        return True

    @staticmethod
    def stop_service(port):
        """停止服务"""
        running, pid = XrayManager.is_running(port)
        if not running or not pid:
            return True

        try:
            process = psutil.Process(pid)
            process.terminate()
            try:
                process.wait(timeout=3)
            except psutil.TimeoutExpired:
                process.kill()
        except psutil.NoSuchProcess:
            pass
        finally:
            pid_file = XrayManager.get_pid_file(port)
            if os.path.exists(pid_file):
                os.remove(pid_file)
        
        return True

    @staticmethod
    def restart_service(port, service_data=None):
        """重启服务"""
        XrayManager.stop_service(port)
        return XrayManager.start_service(port, service_data)
