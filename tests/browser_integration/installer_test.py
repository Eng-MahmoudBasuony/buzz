import importlib.util
import json
from pathlib import Path
import plistlib

import pytest

pytest.importorskip("fcntl", reason="The macOS browser bridge requires POSIX file locks")

from buzz.browser_integration.protocol import ORIGIN


def installer():
    path = Path(__file__).parents[2] / "scripts/install_browser_extension.py"
    spec = importlib.util.spec_from_file_location("browser_installer_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_installer_scopes_host_to_one_extension_and_keeps_credentials_out(tmp_path):
    app = tmp_path / "Buzz.app"
    exe = app / "Contents/MacOS/Buzz"
    exe.parent.mkdir(parents=True)
    exe.write_text("fixture executable")
    exe.chmod(0o755)
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"MBBrowserBridgeProtocol": "1"}))
    home = tmp_path / "home"
    path = installer().install(app, home)
    value = json.loads(path.read_text())
    assert value["path"] == str(exe)
    assert value["allowed_origins"] == [ORIGIN]
    assert value["type"] == "stdio"
    assert "key" not in value
    enabled = home / "Library/Application Support/Buzz/browser-bridge/enabled.json"
    assert json.loads(enabled.read_text()) == {"enabled": True, "origin": ORIGIN}


def test_old_build_is_rejected_before_registration(tmp_path):
    app = tmp_path / "Buzz.app"
    exe = app / "Contents/MacOS/Buzz"
    exe.parent.mkdir(parents=True)
    exe.write_text("fixture")
    exe.chmod(0o755)
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({}))
    with pytest.raises(ValueError):
        installer().install(app, tmp_path / "home")
    assert not (tmp_path / "home").exists()
