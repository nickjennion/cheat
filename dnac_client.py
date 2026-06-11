import requests
import json
from typing import Dict, List, Optional
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


class DNACClient:
    def __init__(self, host: str, username: str, password: str, verify_ssl: bool = False):
        self.host = host
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.token: Optional[str] = None
        self.base_url = f"https://{host}"

    def authenticate(self) -> bool:
        """Get authentication token from DNAC."""
        try:
            auth_url = f"{self.base_url}/dna/system/api/v1/auth/token"
            response = requests.post(
                auth_url,
                auth=(self.username, self.password),
                verify=self.verify_ssl,
                timeout=10
            )
            response.raise_for_status()
            self.token = response.json().get("Token")
            return bool(self.token)
        except requests.exceptions.RequestException as e:
            print(f"Authentication failed: {e}")
            return False

    def get_devices(self) -> List[Dict]:
        """Get list of all devices from DNAC."""
        if not self.token:
            print("Not authenticated. Call authenticate() first.")
            return []

        try:
            devices_url = f"{self.base_url}/dna/intent/api/v1/network-device"
            headers = {"X-Auth-Token": self.token}
            response = requests.get(
                devices_url,
                headers=headers,
                verify=self.verify_ssl,
                timeout=10
            )
            response.raise_for_status()
            devices = response.json().get("response", [])
            return devices
        except requests.exceptions.RequestException as e:
            print(f"Failed to get devices: {e}")
            return []

    def query_devices_by_hostname(self, hostname: str) -> List[Dict]:
        """Query devices by hostname pattern."""
        if not self.token:
            print("Not authenticated. Call authenticate() first.")
            return []

        try:
            query_url = f"{self.base_url}/dna/intent/api/v1/network-device?hostname={hostname}"
            headers = {"X-Auth-Token": self.token}
            response = requests.get(
                query_url,
                headers=headers,
                verify=self.verify_ssl,
                timeout=10
            )
            response.raise_for_status()
            devices = response.json().get("response", [])
            return devices
        except requests.exceptions.RequestException as e:
            print(f"Failed to query devices: {e}")
            return []
