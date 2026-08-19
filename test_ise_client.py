"""Unit tests for the ISE client and parser (no SDK / no network)."""

from types import SimpleNamespace


class _FakeEndpoints:
    """Fake api.endpoints — yields one page of resources per iteration."""

    def __init__(self, pages):
        self._pages = pages
        self.calls = 0

    def get_endpoints_generator(self):
        self.calls += 1
        for resources in self._pages:
            search = SimpleNamespace(resources=resources)
            yield SimpleNamespace(response=SimpleNamespace(SearchResult=search))


class _FakeApi:
    def __init__(self, pages, groups=None):
        self.endpoints = _FakeEndpoints(pages)
        self._groups = groups or {}

    def endpoint_group(self):
        return self


def _res(**kw):
    base = dict(id="E1", name="ep-1", mac="0011.2233.4455", description="",
                profileId="", groupId="G1", portalUser="",
                staticGroupAssignment=True, staticProfileAssignment=False)
    base.update(kw)
    return SimpleNamespace(**base)


def test_get_endpoints_returns_all_pages():
    from ise_client import ISEClient, ISEConfig
    api = _FakeApi([
        [_res(id="E1", name="a"), _res(id="E2", name="b")],
        [_res(id="E3", name="c")],
    ])
    client = ISEClient(ISEConfig("ise.example.net", "u", "p"), api=api)
    eps = client.get_endpoints()
    assert [e.name for e in eps] == ["a", "b", "c"]
    assert api.endpoints.calls == 1


def test_get_endpoints_handles_empty_pages():
    from ise_client import ISEClient, ISEConfig
    api = _FakeApi([[]])
    client = ISEClient(ISEConfig("ise.example.net", "u", "p"), api=api)
    assert client.get_endpoints() == []


def test_sdk_missing_raises_clear_error(monkeypatch):
    from ise_client import ISEClient, ISEConfig, ISESDKMissingError
    import builtins
    real_import = builtins.__import__

    def broken_import(name, *a, **kw):
        if name == "ciscoisesdk":
            raise ImportError("no module")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", broken_import)
    client = ISEClient(ISEConfig("ise.example.net", "u", "p"))
    try:
        client.get_endpoints()
    except ISESDKMissingError as e:
        assert "pip install ciscoisesdk" in str(e)
    else:
        raise AssertionError("expected ISESDKMissingError")


def test_get_endpoint_group_name_resolves_name():
    from ise_client import ISEClient, ISEConfig
    api = _FakeApi([[]])
    client = ISEClient(ISEConfig("ise.example.net", "u", "p"), api=api)
    assert client.get_endpoint_group_name("") is None
