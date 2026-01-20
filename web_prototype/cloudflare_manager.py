import requests
import logging

logger = logging.getLogger(__name__)

class CloudflareManager:
    def __init__(self, api_token, zone_id):
        self.api_token = api_token
        self.zone_id = zone_id
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

    def update_dns_record(self, domain, new_ip):
        """
        更新指定域名的 DNS A 记录
        :param domain: 完整域名 (e.g., node1.example.com)
        :param new_ip: 新的 IP 地址
        :return: bool 是否成功
        """
        try:
            # 1. 获取 DNS 记录 ID
            record = self._get_dns_record(domain)
            if not record:
                logger.error(f"Cloudflare: 未找到域名 {domain} 的 DNS 记录")
                return False

            record_id = record['id']
            old_ip = record['content']

            if old_ip == new_ip:
                logger.info(f"Cloudflare: 域名 {domain} IP 已是 {new_ip}，无需更新")
                return True

            # 2. 更新记录
            url = f"{self.base_url}/zones/{self.zone_id}/dns_records/{record_id}"
            data = {
                "type": "A",
                "name": domain,
                "content": new_ip,
                "ttl": 1, # 自动 TTL
                "proxied": record['proxied'] # 保持原有代理状态
            }
            
            response = requests.put(url, headers=self.headers, json=data)
            result = response.json()
            
            if result.get('success'):
                logger.info(f"Cloudflare: 成功将 {domain} 更新为 {new_ip}")
                return True
            else:
                logger.error(f"Cloudflare: 更新失败: {result.get('errors')}")
                return False

        except Exception as e:
            logger.error(f"Cloudflare API 异常: {e}")
            return False

    def _get_dns_record(self, domain):
        """获取 DNS 记录信息"""
        url = f"{self.base_url}/zones/{self.zone_id}/dns_records"
        params = {
            "name": domain,
            "type": "A"
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            result = response.json()
            
            if result.get('success') and result.get('result'):
                return result['result'][0] # 返回第一条匹配记录
            return None
        except Exception as e:
            logger.error(f"Cloudflare 获取记录异常: {e}")
            return None
