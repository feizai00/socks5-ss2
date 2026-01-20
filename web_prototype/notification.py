import requests
import logging
from database import get_db

logger = logging.getLogger(__name__)

class NotificationManager:
    @staticmethod
    def get_settings():
        """获取通知配置"""
        try:
            db = get_db()
            settings = {}
            cursor = db.execute("SELECT key, value FROM system_settings WHERE key IN ('tg_bot_token', 'tg_chat_id')")
            for row in cursor:
                settings[row['key']] = row['value']
            return settings
        except Exception as e:
            logger.error(f"获取通知配置失败: {e}")
            return {}

    @staticmethod
    def send_telegram_message(message):
        """发送 Telegram 消息"""
        try:
            settings = NotificationManager.get_settings()
            token = settings.get('tg_bot_token')
            chat_id = settings.get('tg_chat_id')

            if not token or not chat_id:
                logger.warning("未配置 Telegram Bot Token 或 Chat ID，跳过发送通知")
                return False

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }

            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info("Telegram 通知发送成功")
                return True
            else:
                logger.error(f"Telegram 通知发送失败: {response.text}")
                return False
        except Exception as e:
            logger.error(f"发送 Telegram 通知异常: {e}")
            return False

    @staticmethod
    def send_healing_alert(service_info, old_ip, new_ip, fail_reason="连接超时"):
        """发送故障修复通知"""
        from datetime import datetime
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        message = (
            f"🚨 *自动故障修复报告*\n\n"
            f"🕒 时间: `{now}`\n"
            f"🏷️ 节点名称: `{service_info.get('node_name', '未知')}`\n"
            f"🔌 服务端口: `{service_info.get('port', '未知')}`\n"
            f"❌ 故障原因: {fail_reason}\n"
            f"🔄 *切换操作*:\n"
            f"   🔴 旧 IP: `{old_ip}`\n"
            f"   🟢 新 IP: `{new_ip}`\n\n"
            f"✅ 服务已重启并恢复连通。"
        )
        return NotificationManager.send_telegram_message(message)
