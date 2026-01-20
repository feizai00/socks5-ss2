import os
import json
import subprocess
import psutil
import logging
import signal
from config import Config
from ssh_manager import SSHManager

logger = logging.getLogger(__name__)

class XrayManager:
    """Xray 管理基类/工厂类"""
    
    @staticmethod
    def get_manager(server_info=None):
        """
        工厂方法：根据服务器信息返回对应的管理器实例
        server_info: dict, 包含 ip, ssh_port, username, password, private_key
        如果 server_info 为 None，则返回本地管理器
        """
        if server_info and server_info.get('ip') and server_info.get('ip') not in ['127.0.0.1', 'localhost']:
            return RemoteXrayManager(server_info)
        return LocalXrayManager()

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

class LocalXrayManager:
    """本地 Xray 管理器"""
    
    def save_config(self, port, config):
        """保存配置文件"""
        service_dir = os.path.join(Config.SERVICE_DIR, str(port))
        os.makedirs(service_dir, exist_ok=True)
        config_path = os.path.join(service_dir, 'config.json')
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return config_path

    def get_pid_file(self, port):
        return os.path.join(Config.SERVICE_DIR, str(port), 'xray.pid')

    def get_log_file(self, port):
        return os.path.join(Config.SERVICE_DIR, str(port), 'xray.log')

    def is_running(self, port):
        """检查服务是否运行"""
        pid_file = self.get_pid_file(port)
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

    def start_service(self, port, service_data=None):
        """启动服务"""
        # 如果提供了数据，先生成配置
        if service_data:
            config = XrayManager.generate_config(service_data)
            self.save_config(port, config)
        
        config_path = os.path.join(Config.SERVICE_DIR, str(port), 'config.json')
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found for port {port}")

        running, _ = self.is_running(port)
        if running:
            return True

        # 检查端口占用
        for conn in psutil.net_connections():
            if conn.laddr and len(conn.laddr) > 1 and conn.laddr[1] == port:
                 # 如果是被占用了，抛出异常
                raise OSError(f"Port {port} is already in use")

        log_file = self.get_log_file(port)
        pid_file = self.get_pid_file(port)

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

    def stop_service(self, port):
        """停止服务"""
        running, pid = self.is_running(port)
        if not running or not pid:
            # 即使进程没运行，也要清理可能残留的 PID 文件
            self._clean_pid_file(port)
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
        except Exception as e:
            logger.error(f"停止服务进程失败: {e}")
        finally:
            self._clean_pid_file(port)
        
        return True

    def _clean_pid_file(self, port):
        """清理 PID 文件，忽略错误"""
        try:
            pid_file = self.get_pid_file(port)
            if os.path.exists(pid_file):
                os.remove(pid_file)
        except Exception as e:
            logger.warning(f"清理 PID 文件失败 (Port {port}): {e}")

    def restart_service(self, port, service_data=None):
        """重启服务"""
        self.stop_service(port)
        return self.start_service(port, service_data)

    def update_config(self, port, service_data):
        """更新配置但不启动"""
        config = XrayManager.generate_config(service_data)
        self.save_config(port, config)

    def get_log_content(self, port, lines=100):
        """获取日志内容"""
        log_file = self.get_log_file(port)
        if not os.path.exists(log_file):
            return ""
        try:
            with open(log_file, 'r') as f:
                # 简单实现，读取最后N行
                return ''.join(f.readlines()[-lines:])
        except Exception:
            return "无法读取日志"


class RemoteXrayManager:
    """远程 Xray 管理器 (SSH)"""
    
    def __init__(self, server_info):
        self.ssh = SSHManager(
            server_info['ip'],
            server_info.get('ssh_port', 22),
            server_info.get('username', 'root'),
            server_info.get('password'),
            server_info.get('private_key')
        )
        self.remote_dir = "/usr/local/xray_services" # 远程工作目录
        self.xray_bin = "/usr/local/bin/xray" # 远程 xray 路径

    def _ensure_remote_env(self):
        """确保远程环境准备就绪"""
        # 创建目录
        self.ssh.exec_command(f"mkdir -p {self.remote_dir}")
        
        # 检查 xray 是否存在
        stdout, _ = self.ssh.exec_command(f"command -v xray")
        if not stdout:
            # 尝试下载 xray (简化版，仅支持 amd64)
            # 实际生产环境应根据架构下载，或者从主控端上传
            install_cmd = "bash -c \"$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)\" @ install"
            self.ssh.exec_command(install_cmd)
            self.xray_bin = "/usr/local/bin/xray" # 默认安装路径
        else:
            self.xray_bin = stdout.strip()

    def start_service(self, port, service_data=None):
        """远程启动服务"""
        if not self.ssh.connect():
            raise ConnectionError("SSH Connection failed")
            
        try:
            self._ensure_remote_env()
            
            service_dir = f"{self.remote_dir}/{port}"
            self.ssh.exec_command(f"mkdir -p {service_dir}")
            
            # 生成配置并上传
            if service_data:
                config = XrayManager.generate_config(service_data)
                # 写入本地临时文件
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
                    json.dump(config, tmp, indent=4)
                    tmp_path = tmp.name
                
                # 上传到远程
                self.ssh.upload_file(tmp_path, f"{service_dir}/config.json")
                os.remove(tmp_path)
            
            # 启动命令
            # 使用 nohup 后台运行，并记录 PID
            cmd = f"nohup {self.xray_bin} run -config {service_dir}/config.json > {service_dir}/xray.log 2>&1 & echo $!"
            stdout, stderr = self.ssh.exec_command(cmd)
            
            if stdout and stdout.isdigit():
                pid = stdout.strip()
                # 保存 PID 到远程文件
                self.ssh.exec_command(f"echo {pid} > {service_dir}/xray.pid")
                return True
            else:
                raise Exception(f"Start failed: {stderr}")
                
        finally:
            self.ssh.close()

    def stop_service(self, port):
        """远程停止服务"""
        if not self.ssh.connect():
            raise ConnectionError("SSH Connection failed")
            
        try:
            service_dir = f"{self.remote_dir}/{port}"
            pid_file = f"{service_dir}/xray.pid"
            
            # 读取 PID
            stdout, _ = self.ssh.exec_command(f"cat {pid_file}")
            if stdout and stdout.strip().isdigit():
                pid = stdout.strip()
                self.ssh.exec_command(f"kill {pid}")
                # 清理 PID 文件
                self.ssh.exec_command(f"rm {pid_file}")
            return True
        finally:
            self.ssh.close()

    def restart_service(self, port, service_data=None):
        self.stop_service(port)
        return self.start_service(port, service_data)

    def update_config(self, port, service_data):
        """更新配置但不启动"""
        if not self.ssh.connect():
            raise ConnectionError("SSH Connection failed")
            
        try:
            self._ensure_remote_env()
            service_dir = f"{self.remote_dir}/{port}"
            self.ssh.exec_command(f"mkdir -p {service_dir}")
            
            # 生成配置并上传
            config = XrayManager.generate_config(service_data)
            # 写入本地临时文件
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
                json.dump(config, tmp, indent=4)
                tmp_path = tmp.name
            
            # 上传到远程
            self.ssh.upload_file(tmp_path, f"{service_dir}/config.json")
            os.remove(tmp_path)
        finally:
            self.ssh.close()

    def is_running(self, port):
        """检查远程服务状态"""
        if not self.ssh.connect():
            return False, None
            
        try:
            service_dir = f"{self.remote_dir}/{port}"
            pid_file = f"{service_dir}/xray.pid"
            
            stdout, _ = self.ssh.exec_command(f"cat {pid_file}")
            if stdout and stdout.strip().isdigit():
                pid = stdout.strip()
                # 检查进程是否存在
                check_cmd = f"ps -p {pid} > /dev/null && echo 'running'"
                status, _ = self.ssh.exec_command(check_cmd)
                if status == 'running':
                    return True, int(pid)
            return False, None
        finally:
            self.ssh.close()

    def get_log_content(self, port, lines=100):
        if not self.ssh.connect():
            return "SSH Connection failed"
        try:
            service_dir = f"{self.remote_dir}/{port}"
            log_file = f"{service_dir}/xray.log"
            stdout, _ = self.ssh.exec_command(f"tail -n {lines} {log_file}")
            return stdout
        finally:
            self.ssh.close()
