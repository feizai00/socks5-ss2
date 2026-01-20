import paramiko
import logging
import socket
from io import StringIO

logger = logging.getLogger(__name__)

class SSHManager:
    def __init__(self, ip, port=22, username='root', password=None, private_key=None):
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.private_key = private_key
        self.client = None

    def connect(self):
        """建立 SSH 连接"""
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            pkey = None
            if self.private_key:
                pkey = paramiko.RSAKey.from_private_key(StringIO(self.private_key))

            self.client.connect(
                hostname=self.ip,
                port=self.port,
                username=self.username,
                password=self.password,
                pkey=pkey,
                timeout=10
            )
            return True
        except Exception as e:
            logger.error(f"SSH 连接失败 ({self.ip}): {e}")
            return False

    def close(self):
        """关闭 SSH 连接"""
        if self.client:
            self.client.close()

    def exec_command(self, command):
        """执行远程命令"""
        if not self.client:
            if not self.connect():
                return None, "Connection failed"
        
        try:
            stdin, stdout, stderr = self.client.exec_command(command)
            return stdout.read().decode().strip(), stderr.read().decode().strip()
        except Exception as e:
            logger.error(f"命令执行失败 ({self.ip}): {e}")
            return None, str(e)

    def upload_file(self, local_path, remote_path):
        """上传文件"""
        if not self.client:
            if not self.connect():
                return False
        
        try:
            sftp = self.client.open_sftp()
            sftp.put(local_path, remote_path)
            sftp.close()
            return True
        except Exception as e:
            logger.error(f"文件上传失败 ({self.ip}): {e}")
            return False

    def test_connection(self):
        """测试连接"""
        if self.connect():
            self.close()
            return True
        return False
