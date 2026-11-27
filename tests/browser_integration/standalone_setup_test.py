import importlib.util
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).parents[2]
HOST = "com.mahmoudbasuony.buzz"
ORIGIN = "chrome-extension://mlaagfgpblngahdpkgkeocdfbndnodgb/"


def packager():
    spec = importlib.util.spec_from_file_location("setup_packager", ROOT / "scripts/package_browser_extension.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def package(tmp_path):
    archive = tmp_path / "setup.zip"
    packager().package(archive)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        if sys.platform != "darwin":
            z.extractall(tmp_path / "extracted")
    if sys.platform == "darwin":
        subprocess.run(["/usr/bin/ditto", "-x", "-k", str(archive), str(tmp_path / "extracted")], check=True)
    return tmp_path / "extracted/Buzz Chrome Setup"


def test_package_contains_only_runtime_assets_and_executable_setup(tmp_path):
    archive = tmp_path / "setup.zip"
    packager().package(archive)
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist()) == {
            "Buzz Chrome Setup/extension/" + name for name in
            ("manifest.json", "popup.html", "popup.js", "popup.css", "icon.png")
        } | {"Buzz Chrome Setup/Install Buzz Extension.command", "Buzz Chrome Setup/Quick Start.html", "Buzz Chrome Setup/LICENSE"}
        installer = z.getinfo("Buzz Chrome Setup/Install Buzz Extension.command")
        assert (installer.external_attr >> 16) & 0o111 == 0o111
        assert z.read("Buzz Chrome Setup/extension/icon.png") == (ROOT / "buzz/assets/buzz-icon-1024.png").read_bytes()
        assert z.read("Buzz Chrome Setup/LICENSE") == (ROOT / "LICENSE").read_bytes()


@pytest.fixture
def environment(tmp_path):
    if sys.platform != "darwin":
        pytest.skip("The standalone installer uses built-in macOS tools")
    app = tmp_path / 'Apps with spaces/تطبيق "Buzz".app'
    exe = app / "Contents/MacOS/Buzz"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    exe.chmod(0o755)
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.chidiwilliams.buzz", "MBBrowserBridgeProtocol": "1"}))
    home = tmp_path / "Home with spaces"
    env = {"BUZZ_SETUP_HOME": str(home), "BUZZ_SETUP_APP_PATH": str(app), "BUZZ_SETUP_NO_OPEN": "1",
           "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8"}
    return home, app, env


def run_setup(package, env):
    return subprocess.run([str(package / "Install Buzz Extension.command")], env=env, capture_output=True, text=True, timeout=20)


def test_setup_works_without_python_or_checkout_and_survives_download_removal(package, environment):
    home, app, env = environment
    result = run_setup(package, env)
    assert result.returncode == 0, result.stderr
    installed = home / "Library/Application Support/Buzz/Chrome/extension"
    assert (installed / "manifest.json").read_bytes() == (package / "extension/manifest.json").read_bytes()
    host = home / f"Library/Application Support/Google/Chrome/NativeMessagingHosts/{HOST}.json"
    assert json.loads(host.read_text(encoding="utf-8")) == {
        "name": HOST, "description": "Send a YouTube video to Buzz", "path": str(app / "Contents/MacOS/Buzz"),
        "type": "stdio", "allowed_origins": [ORIGIN],
    }
    assert host.stat().st_mode & 0o777 == 0o600
    enabled = home / "Library/Application Support/Buzz/browser-bridge/enabled.json"
    assert json.loads(enabled.read_text(encoding="utf-8")) == {"enabled": True, "origin": ORIGIN}
    shutil.rmtree(package)
    assert (installed / "popup.js").is_file()
    assert json.loads(host.read_text(encoding="utf-8"))["path"] == str(app / "Contents/MacOS/Buzz")


def test_rerun_preserves_user_data_and_jobs(package, environment):
    home, app, env = environment
    assert run_setup(package, env).returncode == 0
    support = home / "Library/Application Support/Buzz"
    protected = {support / "Buzz.sqlite": b"existing database", support / "browser-bridge/abcdefghijk.json": b"existing job"}
    for path, data in protected.items(): path.write_bytes(data)
    assert run_setup(package, env).returncode == 0
    for path, data in protected.items(): assert path.read_bytes() == data
    assert not list(support.glob(".chrome-setup.*"))


def test_old_app_fails_before_changing_user_folders(package, environment):
    home, app, env = environment
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.chidiwilliams.buzz"}))
    result = run_setup(package, env)
    assert result.returncode != 0
    assert not home.exists()


def test_other_folder_is_not_replaced(package, environment):
    home, app, env = environment
    destination = home / "Library/Application Support/Buzz/Chrome"
    destination.mkdir(parents=True)
    existing = destination / "personal.txt"
    existing.write_text("keep", encoding="utf-8")
    assert run_setup(package, env).returncode != 0
    assert existing.read_text(encoding="utf-8") == "keep"


def test_symlinked_bridge_is_not_followed(package, environment, tmp_path):
    home, app, env = environment
    support = home / "Library/Application Support/Buzz"
    support.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    (support / "browser-bridge").symlink_to(external)
    assert run_setup(package, env).returncode != 0
    assert not list(external.iterdir())
