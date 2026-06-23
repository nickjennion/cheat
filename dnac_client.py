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
        """Get list of all devices from DNAC (with pagination using offset/limit)."""
        if not self.token:
            print("Not authenticated. Call authenticate() first.")
            return []

        all_devices = []
        offset = 0
        limit = 500
        page = 1

        try:
            print("  Fetching device pages...", flush=True)
            while True:
                print(f"  [Page {page}] offset={offset}, limit={limit}...", end=" ", flush=True)
                devices_url = f"{self.base_url}/dna/intent/api/v1/network-device"
                headers = {"X-Auth-Token": self.token}
                params = {"offset": offset, "limit": limit}

                print(f"\n    DEBUG: URL={devices_url}", flush=True)
                print(f"    DEBUG: params={params}", flush=True)
                print(f"    DEBUG: headers={headers}", flush=True)

                response = requests.get(
                    devices_url,
                    headers=headers,
                    params=params,
                    verify=self.verify_ssl,
                    timeout=30
                )

                print(f"    DEBUG: Status={response.status_code}", flush=True)
                print(f"    DEBUG: Response text={response.text[:500]}", flush=True)

                response.raise_for_status()
                devices = response.json().get("response", [])

                print(f"got {len(devices)} devices (total: {len(all_devices) + len(devices)})", flush=True)

                if not devices:
                    print("  [No devices returned - pagination complete]", flush=True)
                    break

                all_devices.extend(devices)

                if len(devices) < limit:
                    print("  [Final page reached - fewer than limit returned]", flush=True)
                    break

                offset += limit
                page += 1

            return all_devices
        except requests.exceptions.RequestException as e:
            print(f"Failed to get devices: {e}")
            return []
            return []

    def query_devices_by_hostname(self, hostname: str) -> List[Dict]:
        """Query devices by hostname pattern (with pagination using offset/limit)."""
        if not self.token:
            print("Not authenticated. Call authenticate() first.")
            return []

        all_devices = []
        offset = 0
        limit = 500

        try:
            while True:
                query_url = f"{self.base_url}/dna/intent/api/v1/network-device"
                headers = {"X-Auth-Token": self.token}
                params = {"hostname": hostname, "offset": offset, "limit": limit}
                response = requests.get(
                    query_url,
                    headers=headers,
                    params=params,
                    verify=self.verify_ssl,
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

    def execute_commands(self, device_id: str, commands: List[str]) -> Optional[str]:
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
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                verify=self.verify_ssl,
                timeout=10
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
            response = requests.get(
                url,
                headers=headers,
                verify=self.verify_ssl,
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
            response = requests.get(
                url,
                headers=headers,
                verify=self.verify_ssl,
                timeout=10
            )
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            print(f"Failed to get file output: {e}")
            return None
