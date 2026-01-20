import time
import logging
import threading
from datetime import datetime
from flask import current_app
from database import get_db, init_db, close_db
from utils import SSLinkUtils
from xray_manager import XrayManager
from notification import NotificationManager
from cloudflare_manager import CloudflareManager
from ssh_manager import SSHManager

logger = logging.getLogger(__name__)

class ServiceHealer:
    def __init__(self, app):
        self.app = app
        self.ss_utils = SSLinkUtils()
        self.running = False
        self.interval = 300  # 默认 5 分钟 (300秒)

    def start(self):
        """启动监控线程"""
        if self.running:
            return
        
        self.running = True
        thread = threading.Thread(target=self._monitor_loop)
        thread.daemon = True
        thread.start()
        logger.info("自动故障修复监控已启动")

    def _monitor_loop(self):
        """监控循环"""
        while self.running:
            try:
                with self.app.app_context():
                    # 1. 检查服务健康状况 (IP池轮换)
                    self._check_and_heal()
                    
                    # 2. 检查服务器健康状况 (故障迁移)
                    self._check_servers_and_failover()
            except Exception as e:
                logger.error(f"监控循环异常: {e}")
            
            # 获取配置的间隔时间
            try:
                with self.app.app_context():
                    db = get_db()
                    setting = db.execute("SELECT value FROM system_settings WHERE key = 'monitor_interval'").fetchone()
                    time.sleep(300) 
            except:
                time.sleep(300)

    def _check_servers_and_failover(self):
        """检查服务器健康并执行故障迁移"""
        db = get_db()
        
        # 检查是否开启
        auto_heal = db.execute("SELECT value FROM system_settings WHERE key = 'auto_heal_enabled'").fetchone()
        if not auto_heal or auto_heal['value'] != 'true':
            return

        # 获取 Cloudflare 配置
        settings = db.execute("SELECT key, value FROM system_settings WHERE key IN ('cf_api_token', 'cf_zone_id')").fetchall()
        cf_config = {row['key']: row['value'] for row in settings}
        cf_manager = None
        if cf_config.get('cf_api_token') and cf_config.get('cf_zone_id'):
            cf_manager = CloudflareManager(cf_config['cf_api_token'], cf_config['cf_zone_id'])

        # 获取所有活跃服务器
        servers = db.execute("SELECT * FROM servers WHERE status != 'inactive'").fetchall()
        
        active_servers = []
        failed_servers = []
        
        for server in servers:
            # 排除本机
            if server['ip'] in ['127.0.0.1', 'localhost']:
                active_servers.append(server)
                continue
                
            # 测试 SSH 连接
            ssh = SSHManager(server['ip'], server['ssh_port'], server['username'], server['password'], server['private_key'])
            if ssh.test_connection():
                active_servers.append(server)
                # 如果之前是 error，恢复为 active
                if server['status'] == 'error':
                    db.execute("UPDATE servers SET status = 'active', last_check = CURRENT_TIMESTAMP WHERE id = ?", (server['id'],))
                    db.commit()
                    NotificationManager.send_telegram_message(f"✅ **服务器恢复**\n服务器 `{server['name']}` ({server['ip']}) 已恢复连接。")
            else:
                # 连接失败
                logger.warning(f"服务器 {server['name']} ({server['ip']}) 连接失败")
                failed_servers.append(server)
                if server['status'] == 'active':
                    db.execute("UPDATE servers SET status = 'error', last_check = CURRENT_TIMESTAMP WHERE id = ?", (server['id'],))
                    db.commit()
                    NotificationManager.send_telegram_message(f"⚠️ **服务器故障**\n服务器 `{server['name']}` ({server['ip']}) 连接失败！")

        # 故障迁移逻辑
        if failed_servers and active_servers and cf_manager:
            for failed in failed_servers:
                if failed['domain']: # 只有绑定了域名的服务器才需要迁移
                    # 寻找一个健康的替代服务器 (简单的策略：找负载最低的，或者随机一个)
                    # 这里简单起见，取第一个健康的服务器
                    target = active_servers[0]
                    
                    logger.info(f"正在执行故障迁移: {failed['name']} -> {target['name']}")
                    
                    # 更新 DNS
                    if cf_manager.update_dns_record(failed['domain'], target['ip']):
                        msg = (f"🔄 **自动故障迁移执行成功**\n"
                               f"故障节点: `{failed['name']}`\n"
                               f"接管节点: `{target['name']}`\n"
                               f"域名 `{failed['domain']}` 已指向 IP `{target['ip']}`")
                        NotificationManager.send_telegram_message(msg)
                    else:
                        NotificationManager.send_telegram_message(f"❌ **故障迁移失败**\n无法更新域名 `{failed['domain']}` 的 DNS 记录。")

    def _check_and_heal(self):
        """检查所有服务并修复故障"""
        db = get_db()
        
        # 1. 检查是否开启自动修复
        auto_heal = db.execute("SELECT value FROM system_settings WHERE key = 'auto_heal_enabled'").fetchone()
        if not auto_heal or auto_heal['value'] != 'true':
            # logger.info("自动修复未开启，跳过检查")
            return

        # 2. 获取所有运行中的服务
        services = db.execute("SELECT * FROM services WHERE status = 'running' AND deleted_at IS NULL").fetchall()
        
        for service in services:
            try:
                port = service['port']
                ss_password = service['ss_password']
                method = service['method'] or 'aes-256-gcm'
                
                # 3. 测试连通性 (访问 tiktok.com)
                # logger.info(f"正在检测服务 {port} ({service['node_name']})...")
                latency = self.ss_utils.test_proxy_connection(port, ss_password, method, timeout=15)
                
                if latency < 0:
                    logger.warning(f"服务 {port} 检测失败，准备进行修复...")
                    self._heal_service(db, service)
                else:
                    pass
                    # logger.info(f"服务 {port} 正常，延迟: {latency}ms")
                    
            except Exception as e:
                logger.error(f"检测服务 {service['port']} 出错: {e}")

    def _heal_service(self, db, service):
        """修复单个服务 (切换 IP)"""
        port = service['port']
        old_ip = service['socks_ip']
        
        # 1. 从 IP 池获取一个新的可用 IP
        new_ip_row = db.execute("""
            SELECT * FROM ip_pool 
            WHERE status = 'available' 
            ORDER BY last_checked_at ASC, id ASC 
            LIMIT 1
        """).fetchone()
        
        if not new_ip_row:
            logger.error(f"IP 池耗尽！无法修复服务 {port}")
            # 可以发送一个警告给管理员
            NotificationManager.send_telegram_message(f"⚠️ **IP 池耗尽警告**\n无法为服务 `{service['node_name']}` ({port}) 找到可用的备用 IP，请尽快补充！")
            return

        try:
            # 2. 更新服务配置
            new_ip = new_ip_row['socks_ip']
            new_port = new_ip_row['socks_port']
            new_user = new_ip_row['socks_user']
            new_pass = new_ip_row['socks_pass']
            
            # 更新数据库
            db.execute("""
                UPDATE services 
                SET socks_ip = ?, socks_port = ?, socks_user = ?, socks_pass = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (new_ip, new_port, new_user, new_pass, service['id']))
            
            # 3. 更新 IP 池状态
            # 将旧 IP 标记为 bad (或者 used，根据策略)
            # 这里我们标记为 bad，并记录信息
            # 实际上，旧 IP 我们不知道是不是真的坏了，但在此服务上它不通。
            # 简单起见，我们把旧 IP 扔掉（不入库），或者如果旧 IP 也在池子里，更新它的状态。
            # 这里的逻辑是：ip_pool 表存储的是“备用”的。一旦使用了，就从 ip_pool 移除？
            # 或者 ip_pool 存储所有 IP？
            # 根据用户描述：“备用池使用的IP是垃圾的IP... 更换的节点名称...”。
            # 我们假设 ip_pool 里的 IP 是一次性的，用一个少一个。
            
            # 将新 IP 标记为 used
            db.execute("UPDATE ip_pool SET status = 'used', last_checked_at = CURRENT_TIMESTAMP WHERE id = ?", (new_ip_row['id'],))
            
            db.commit()
            
            # 4. 重启 Xray 服务
            # 获取最新的服务数据
            updated_service = db.execute("SELECT * FROM services WHERE id = ?", (service['id'],)).fetchone()
            service_data = dict(updated_service) # 转换为字典
            
            # 获取服务器信息
            server_info = None
            if updated_service['server_id']:
                server = db.execute("SELECT * FROM servers WHERE id = ?", (updated_service['server_id'],)).fetchone()
                if server:
                    server_info = dict(server)
            
            manager = XrayManager.get_manager(server_info)
            manager.restart_service(port, service_data)
            logger.info(f"服务 {port} 已切换到新 IP: {new_ip}")
            
            # 5. 发送通知
            NotificationManager.send_healing_alert(
                service_info=service,
                old_ip=old_ip,
                new_ip=new_ip,
                fail_reason="TikTok 连通性测试失败"
            )
            
        except Exception as e:
            logger.error(f"修复服务 {port} 失败: {e}")
            db.rollback()

