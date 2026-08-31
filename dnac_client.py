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
        self.retry_total = retry_total
        self.retry_backoff = retry_backoff
        self.token: Optional[str] = None
        self.base_url = f"https://{host}"
        self.session = self._new_session()

    def _new_session(self) -> requests.Session:
        """Create an independently configured API session.

        Authentication uses a new instance so cookies or default headers from
        the long-lived data session cannot contaminate a token-mint request.
        """
        session = requests.Session()
        session.verify = self.verify_ssl
        retry_strategy = urllib3.Retry(
            total=self.retry_total,
            backoff_factor=self.retry_backoff,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        return session

    @staticmethod
    def _auth_error_detail(response) -> str:
        """Extract a short error description without exposing a token."""
        try:
            payload = response.json()
        except (ValueError, TypeError):
            return ""

        def find_message(value):
            if not isinstance(value, dict):
                return ""
            for key in ("message", "detail", "error", "errorMessage"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
            for candidate in value.values():
                found = find_message(candidate)
                if found:
                    return found
            return ""

        return " ".join(find_message(payload).split())[:300]

    def authenticate(self) -> bool:
        """Mint a DNAC token, atomically replacing the previous token."""
        auth_session = self._new_session()
        try:
            auth_url = f"{self.base_url}/dna/system/api/v1/auth/token"
            response = auth_session.post(
                auth_url,
                auth=(self.username, self.password),
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            payload = response.json()
            new_token = payload.get("Token") if isinstance(payload, dict) else None
            if not isinstance(new_token, str) or not new_token.strip():
                print("Authentication failed: token endpoint returned no valid Token")
                return False
            new_token = new_token.strip()
            self.token = new_token
            self._save_token(new_token)
            return True
        except requests.exceptions.RequestException as e:
            response = getattr(e, "response", None)
            if response is not None:
                status = getattr(response, "status_code", "unknown")
                reason = getattr(response, "reason", "") or ""
                detail = self._auth_error_detail(response)
                label = f"HTTP {status}" + (f" {reason}" if reason else "")
                print(f"Authentication failed ({label})" + (f": {detail}" if detail else ""))
            else:
                print(f"Authentication failed: {e}")
            return False
        except (ValueError, TypeError) as e:
            print(f"Authentication failed: invalid token response ({e})")
            return False
        finally:
            auth_session.close()

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

    def search_clients(
        self,
        mac_prefix: str,
        device_name: Optional[str] = None,
        limit: int = 500,
    ) -> list:
        """Search clients by MAC prefix wildcard via /dna/data/api/v1/clients.

        mac_prefix should be at least 4 hex chars (e.g. '00:11' or '0011').
        A trailing '*' is appended automatically if not already present.
        device_name filters by connectedNetworkDeviceName (wildcard supported).
        Returns a flat list of client dicts across all pages.
        """
        if not self.token:
            print("Not authenticated.")
            return []

        if not mac_prefix.endswith("*"):
            mac_prefix = mac_prefix + "*"

        all_clients: list = []
        offset = 1
        page = 1

        try:
            while True:
                params: dict = {
                    "macAddress": mac_prefix,
                    "limit": limit,
                    "offset": offset,
                }
                if device_name:
                    if not device_name.endswith("*"):
                        device_name = device_name + "*"
                    params["connectedNetworkDeviceName"] = device_name

                print(f"  [Page {page}] querying clients...", end=" ", flush=True)
                url = f"{self.base_url}/dna/data/api/v1/clients"
                response = self.session.get(
                    url,
                    headers={"X-Auth-Token": self.token},
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                batch = data.get("response", [])
                total = data.get("page", {}).get("count", len(batch))
                print(f"got {len(batch)} (total: {total})", flush=True)

                all_clients.extend(batch)
                if len(batch) < limit:
                    break
                offset += limit
                page += 1

        except Exception as e:
            print(f"  client search error: {e}")

        return all_clients

    def lookup_client(self, mac: str) -> Optional[Dict]:
        """Look up a client by exact MAC address via Assurance client-detail.

        Returns the 'detail' dict on success (includes nasIdentifier, nasPortId,
        vlanId, connectionStatus, ipv4, hostName, deviceType). Returns None if
        the client is not found or Assurance is unavailable.
        """
        if not self.token:
            print("Not authenticated.")
            return None
        try:
            url = f"{self.base_url}/dna/intent/api/v1/client-detail"
            headers = {"X-Auth-Token": self.token}
            response = self.session.get(
                url,
                headers=headers,
                params={"macAddress": mac},
                timeout=10,
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json().get("detail") or None
        except Exception as e:
            print(f"  client-detail error: {e}")
            return None

    def search_clients_by_ip(
        self,
        ip_prefix: str,
        device_name: Optional[str] = None,
        limit: int = 500,
    ) -> list:
        """Search clients by IP address prefix via /dna/data/api/v1/clients.

        ip_prefix supports wildcards (e.g. '10.1.2.*').
        A trailing '*' is appended automatically if not already present.
        device_name filters by connectedNetworkDeviceName (wildcard supported).
        Returns a flat list of client dicts across all pages.
        """
        if not self.token:
            print("Not authenticated.")
            return []

        if not ip_prefix.endswith("*"):
            ip_prefix = ip_prefix + "*"

        all_clients: list = []
        offset = 1
        page = 1

        try:
            while True:
                params: dict = {
                    "ipv4Address": ip_prefix,
                    "limit": limit,
                    "offset": offset,
                }
                if device_name:
                    if not device_name.endswith("*"):
                        device_name = device_name + "*"
                    params["connectedNetworkDeviceName"] = device_name

                print(f"  [Page {page}] querying clients...", end=" ", flush=True)
                url = f"{self.base_url}/dna/data/api/v1/clients"
                response = self.session.get(
                    url,
                    headers={"X-Auth-Token": self.token},
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                batch = data.get("response", [])
                total = data.get("page", {}).get("count", len(batch))
                print(f"got {len(batch)} (total: {total})", flush=True)

                all_clients.extend(batch)
                if len(batch) < limit:
                    break
                offset += limit
                page += 1

        except Exception as e:
            print(f"  IP search error: {e}")

        return all_clients

    def get_sites(self) -> List[Dict]:
        """Get all sites from DNAC site hierarchy."""
        if not self.token:
            print("Not authenticated.")
            return []
        try:
            r = self.session.get(
                f"{self.base_url}/dna/intent/api/v1/site",
                headers={"X-Auth-Token": self.token},
                timeout=30,
            )
            r.raise_for_status()
            return r.json().get("response", [])
        except Exception as e:
            print(f"Failed to get sites: {e}")
            return []

    def get_ap_devices(self) -> list[dict]:
        """Get all Unified AP devices from DNAC inventory (paginated)."""
        if not self.token:
            print("Not authenticated.")
            return []

        all_aps = []
        offset = 1
        limit = 500
        page = 1

        try:
            while True:
                print(f"  [Page {page}] fetching APs {offset}-{offset + limit - 1}...", end=" ", flush=True)
                r = self.session.get(
                    f"{self.base_url}/dna/intent/api/v1/network-device",
                    headers={"X-Auth-Token": self.token},
                    params={"family": "Unified AP", "offset": offset, "limit": limit},
                    timeout=30,
                )
                r.raise_for_status()
                batch = r.json().get("response", [])
                print(f"got {len(batch)} (total: {len(all_aps) + len(batch)})", flush=True)
                if not batch:
                    break
                all_aps.extend(batch)
                if len(batch) < limit:
                    break
                offset += limit
                page += 1
        except Exception as e:
            print(f"Failed to get AP devices: {e}")
            return []

        return all_aps

    def get_ap_topology(self, ap_ids: list[str]) -> tuple[dict[str, str | None], bool]:
        """Get current upstream switch+port for each AP via physical topology.

        Returns ({ap_id: "switch (port)" | None}, error_bool).
        None means the AP has no link (offline/unmanaged).
        error_bool is True if the API call itself failed.
        """
        if not self.token:
            return {}, True

        try:
            r = self.session.get(
                f"{self.base_url}/dna/intent/api/v1/topology/physical-topology",
                headers={"X-Auth-Token": self.token},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json().get("response", {})
            nodes = {n["id"]: n.get("label") or n.get("id", "") for n in data.get("nodes", [])}
            ap_set = set(ap_ids)
            result: dict[str, str | None] = {ap_id: None for ap_id in ap_ids}

            for link in data.get("links", []):
                src = link.get("source", "")
                tgt = link.get("target", "")
                if tgt in ap_set:
                    sw = nodes.get(src, src)
                    port = link.get("startPortName", "")
                    result[tgt] = f"{sw} ({port})" if port else sw
                elif src in ap_set:
                    sw = nodes.get(tgt, tgt)
                    port = link.get("endPortName", "")
                    result[src] = f"{sw} ({port})" if port else sw

            return result, False

        except Exception as e:
            print(f"  Topology fetch error: {e}")
            return {}, True

    def get_ap_events(self, ap_ids: list[str], hours: int = 24) -> tuple[dict[str, str | None], bool]:
        """Get last-known upstream before current connection via Assurance events.

        Queries /dna/data/api/v1/assuranceEvents for each AP over the last `hours`
        hours. Looks for connectivity events that include previous neighbor info.

        NOTE: Exact event field names (previousNeighborHostname, previousNeighborPort,
        neighborHostname, neighborPort) should be validated against the target DNAC
        environment. The fallback snapshot approach is documented in the design spec
        if this endpoint proves unreliable.

        Returns ({ap_id: "switch (port)" | None}, error_bool).
        None means no relevant events were found in the window.
        error_bool is True only if authentication is missing.
        """
        if not self.token:
            return {}, True

        import time as _time
        end_ms = int(_time.time() * 1000)
        start_ms = end_ms - (hours * 3600 * 1000)
        result: dict[str, str | None] = {ap_id: None for ap_id in ap_ids}

        for ap_id in ap_ids:
            try:
                r = self.session.get(
                    f"{self.base_url}/dna/data/api/v1/assuranceEvents",
                    headers={"X-Auth-Token": self.token},
                    params={
                        "deviceId": ap_id,
                        "startTime": start_ms,
                        "endTime": end_ms,
                    },
                    timeout=30,
                )
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                events = r.json().get("response", [])

                for event in sorted(events, key=lambda e: e.get("timestamp", 0), reverse=True):
                    details = event.get("details") or {}
                    host = (details.get("previousNeighborHostname")
                            or details.get("neighborHostname")
                            or "")
                    port = (details.get("previousNeighborPort")
                            or details.get("neighborPort")
                            or "")
                    if host:
                        result[ap_id] = f"{host} ({port})" if port else host
                        break

            except Exception as e:
                print(f"  Events fetch error for {ap_id}: {e}")
                # result[ap_id] remains None → renders as "— (no data)"

        return result, False

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
