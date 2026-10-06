from echo.extensions.registry import ExtensionRegistry


def test_optional_invalid_manifest_does_not_prevent_startup(tmp_path):
    bad = tmp_path / "broken"
    bad.mkdir()
    (bad / "extension.yaml").write_text("schema_version: '999'\nid: broken\n")
    registry = ExtensionRegistry.load(tmp_path, isolate_invalid=True)
    assert registry.describe() == [{"id": "broken", "status": "INVALID_CONFIGURATION", "enabled": False, "capabilities": [], "adapter_available": False}]
    assert registry.find("supplier_discovery") == []
