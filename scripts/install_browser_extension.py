"""Register the local Chrome bridge. Run with uv; never reads API credentials."""
import argparse
import os
import plistlib
import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from buzz.browser_integration import HOST_NAME, EXTENSION_ID
from buzz.browser_integration.protocol import Store, ORIGIN, atomic_json


def install(app, home):
    app = Path(app).resolve()
    executable = app / "Contents/MacOS/Buzz"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError("Install the browser-enabled macOS Buzz.app first")
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    if info.get("MBBrowserBridgeProtocol") != "1":
        raise ValueError("This Buzz build does not include the browser bridge; install the matching build first")
    base = Path(home) / "Library/Application Support"
    store = Store(base / "Buzz/browser-bridge")
    atomic_json(store.root / "enabled.json", {"enabled": True, "origin": ORIGIN})
    target = base / "Google/Chrome/NativeMessagingHosts"
    target.mkdir(parents=True, exist_ok=True)
    atomic_json(target / (HOST_NAME + ".json"), {
        "name": HOST_NAME, "description": "Send a YouTube video to Buzz",
        "path": str(executable), "type": "stdio", "allowed_origins": [ORIGIN],
    })
    return target / (HOST_NAME + ".json")


def prepare_extension():
    # Reuse the original tracked artwork; the generated copy is not source.
    shutil.copyfile(ROOT / "buzz/assets/buzz-icon-1024.png", ROOT / "browser-extension/icon.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", default="/Applications/Buzz.app")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("This installer currently supports macOS and Google Chrome only")
    registered = install(args.app, Path.home())
    prepare_extension()
    print("Registered:", registered)
    print("Chrome extension ID:", EXTENSION_ID)
    print("Load unpacked folder:", ROOT / "browser-extension")
