import requests
import json
import urllib3
from typing import Dict, List, Optional
from urllib3.exceptions import InsecureRequestWarning
from requests.adapters import HTTPAdapter

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


class DNACClient:
    def __init__(self, host: str, username: str, password: str, verify_ssl: bool = False,
                 retry_total: int = 3, retry_backoff: int = 1):
        self.host = host
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.token: Optional[str] = None
        self.base_url = f"https://{host}"
        self.session = requests.Session()
        self.session.verify = verify_ssl
        retry_strategy = urllib3.Retry(
            total=retry_total,
            backoff_factor=retry_backoff,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

    def authenticate(self) -> bool:
        """Get authentication token from DNAC."""
        try:
            auth_url = f"{self.base_url}/dna/system/api/v1/auth/token"
            response = self.session.post(
                auth_url,
                auth=(self.username, self.password),
                timeout=10
            )
            response.raise_for_status()
            self.token = response.json().get("Token")
            if self.token:
                self._save_token(self.token)
            return bool(self.token)
        except requests.exceptions.RequestException as e:
            print(f"Authentication failed: {e}")
            return False

    @staticmethod
    def _save_token(token: str) -> None:
        """Persist the issued token to token.env for reuse/inspection."""
        try:
            with open("token.env", "w") as f:
                f.write(f"DNAC_TOKEN={token}\n")
        except IOError as e:
            print(f"Warning: could not write token.env: {e}")

    def get_devices(self) -> List[Dict]:
        """Get list of all devices from DNAC (with pagination using offset/limit)."""
        if not self.token:
            print("Not authenticated. Call authenticate() first.")
            return []

        all_devices = []
        offset = 1
        limit = 500
        page = 1

        try:
            while True:
                print(f"  [Page {page}] fetching devices {offset}-{offset + limit - 1}...", end=" ", flush=True)
                devices_url = f"{self.base_url}/dna/intent/api/v1/network-device"
                headers = {"X-Auth-Token": self.token}
                params = {"offset": offset, "limit": limit}
                response = self.session.get(
                    devices_url,
                    headers=headers,
                    params=params,
                    timeout=30
                )
                response.raise_for_status()
                devices = response.json().get("response", [])

                print(f"got {len(devices)} (total: {len(all_devices) + len(devices)})", flush=True)

                if not devices:
                    break

                all_devices.extend(devices)

                if len(devices) < limit:
                    break

                offset += limit
                page += 1

            return all_devices
        except requests.exceptions.RequestException as e:
            print(f"Failed to get devices: {e}")
            return []

    def query_devices_by_hostname(self, hostname: str) -> List[Dict]:
        """Query devices by hostname pattern (with pagination using offset/limit)."""
        if not self.token:
            print("Not authenticated. Call authenticate() first.")
            return []

        all_devices = []
        offset = 1
        limit = 500

        try:
            while True:
                query_url = f"{self.base_url}/dna/intent/api/v1/network-device"
                headers = {"X-Auth-Token": self.token}
                params = {"hostname": hostname, "offset": offset, "limit": limit}
                response = self.session.get(
                    query_url,
                    headers=headers,
                    params=params,
                    timeout=30
                )
                response.raise_for_status()
                devices = response.json().get("response", [])

                if not devices:
                    break

                all_devices.extend(devices)

                if len(devices) < limit:
                    break

                offset += limit

            return all_devices
        except requests.exceptions.RequestException as e:
            print(f"Failed to query devices: {e}")
            return []

    def enable_slow_mode(self) -> None:
        """Rebuild retry adapter with backoff_factor=2 (doubled from default 1)."""
        retry_strategy = urllib3.Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

    def execute_commands(self, device_id: str, commands: List[str], timeout: int = 10) -> Optional[str]:
        """Execute commands on a device via Command Runner. Returns task ID."""
        if not self.token:
            print("Not authenticated.")
            return None

        try:
            url = f"{self.base_url}/dna/intent/api/v1/network-device-poller/cli/read-request"
            headers = {"X-Auth-Token": self.token, "Content-Type": "application/json"}
            payload = {
                "name": "cmd-run",
                "deviceUuids": [device_id],
                "commands": commands
            }
            response = self.session.post(
                url,
                json=payload,
                headers=headers,
                timeout=timeout
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", {}).get("taskId")
        except requests.exceptions.RequestException as e:
            print(f"Failed to execute commands: {e}")
            return None

    def get_task_result(self, task_id: str) -> Optional[Dict]:
        """Get results from a completed Command Runner task."""
        if not self.token:
            print("Not authenticated.")
            return None

        try:
            url = f"{self.base_url}/dna/intent/api/v1/task/{task_id}"
            headers = {"X-Auth-Token": self.token}
            response = self.session.get(
                url,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json().get("response", {})
        except requests.exceptions.RequestException as e:
            print(f"Failed to get task result: {e}")
            return None

    def get_file_output(self, file_id: str) -> Optional[str]:
        """Fetch file output from Command Runner results."""
        if not self.token:
            print("Not authenticated.")
            return None

        try:
            url = f"{self.base_url}/dna/intent/api/v1/file/{file_id}"
            headers = {"X-Auth-Token": self.token}
            response = self.session.get(
                url,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            print(f"Failed to get file output: {e}")
            return None
