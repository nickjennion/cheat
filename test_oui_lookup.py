from oui_lookup import clear_cache, lookup_manufacturer


def test_oui_lookup_uses_bundled_database():
    clear_cache()
    assert lookup_manufacturer("0000.0c9f.0001") == "Cisco Systems, Inc"
    assert lookup_manufacturer("not-a-mac") == "Unknown"
