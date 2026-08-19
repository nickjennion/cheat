"""
ISE REST API client wrapping Cisco's official `ciscoisesdk`.

Thin layer over `IdentityServicesEngineAPI`: instantiate with the same
host/username/password the user picked on the CHEAT Menu 1 screen (the DNAC
env file may also carry an optional ISE_HOST line), then query endpoints.

The SDK import is deferred so the rest of CHEAT works without ciscoisesdk
installed — ISE use reports a clear message instead of crashing at startup.
An `api` may be injected for offline tests (matching DNACClient's style).
"""

from dataclasses import dataclass
from typing import Optional


class ISESDKMissingError(RuntimeError):
    """Raised when ciscoisesdk is not installed."""


@dataclass
class ISEConfig:
    """Connection settings for one ISE controller (mirrors the env file keys)."""
    host: str
    username: str
    password: str
    version: str = "3.3_patch_1"   # latest ISE API version
    verify_ssl: bool = False


class ISEClient:
    def __init__(self, config: ISEConfig, api=None):
        self.config = config
        self._api = api

    # =========================================================================
    # Connection
    # =========================================================================

    def _connect(self):
        """Lazily import and instantiate the SDK. Returns the api object."""
        if self._api is not None:
            return self._api
        try:
            from ciscoisesdk import IdentityServicesEngineAPI
        except ImportError as e:
            raise ISESDKMissingError(
                "The Cisco ISE SDK is not installed — run "
                "`pip install ciscoisesdk` to use ISE features."
            ) from e

        cfg = self.config
        self._api = IdentityServicesEngineAPI(
            username=cfg.username,
            password=cfg.password,
            base_url=f"https://{cfg.host}",
            uses_api_gateway=True,
            verify=cfg.verify_ssl,
            version=cfg.version,
        )
        return self._api

    # =========================================================================
    # Endpoints
    # =========================================================================

    def get_endpoints(self) -> list:
        """Return every ISE endpoint across all pages.

        Each item is the SDK's endpoint resource object (id, name, description,
        mac, profileId, groupId, portalUser, ...). Pagination is handled by the
        SDK's generator, so no offset bookkeeping is needed here.
        """
        api = self._connect()
        endpoints: list = []
        for page in api.endpoints.get_endpoints_generator():
            search = page.response.SearchResult
            if search and search.resources:
                endpoints.extend(search.resources)
        return endpoints

    def get_endpoint_group_name(self, group_id: str) -> Optional[str]:
        """Resolve an endpoint-group id to its name, or None on failure."""
        if not group_id:
            return None
        try:
            api = self._connect()
            resp = api.endpoint_group.get_by_id(group_id)
            group = resp.response.EndpointGroup
            return getattr(group, "name", None)
        except Exception:
            return None
