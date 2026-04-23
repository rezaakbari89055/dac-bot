import aiohttp
import json

class XuiAPI:
    def __init__(self, panel_url, username, password):
        self.panel_url = panel_url
        self.username = username
        self.password = password
        self.session = aiohttp.ClientSession()
        self.cookie = None

    async def login(self):
        try:
            url = f"{self.panel_url}/login"
            payload = {"username": self.username, "password": self.password}
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    self.cookie = response.cookies.get("session")
                    return True
            return False
        except:
            return False

    async def add_client(self, inbound_id, uuid, email, expiry_time, traffic_limit_gb):
        if not self.cookie: return False
        try:
            expiry = int(expiry_time.timestamp() * 1000)
            traffic = int(traffic_limit_gb * 1024 * 1024 * 1024)
            url = f"{self.panel_url}/inbounds/addClient"
            payload = {
                "id": inbound_id,
                "settings": json.dumps({"clients": [{"id": uuid, "flow": "", "email": email, "limitIp": 0, "totalGB": traffic, "expiryTime": expiry}]})
            }
            headers = {"Cookie": f"session={self.cookie}"}
            async with self.session.post(url, json=payload, headers=headers) as response:
                return response.status == 200
        except:
            return False

    async def get_client_usage(self, inbound_id, email):
        # یک تابع نمونه برای دریافت مصرف
        return 0
