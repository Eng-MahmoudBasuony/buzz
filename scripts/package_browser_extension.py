"""Build the standalone macOS Chrome setup ZIP using uv and the standard library."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_FILES = ("manifest.json", "popup.html", "popup.js", "popup.css")
ARCHIVE_ROOT = "Buzz Chrome Setup"


def package(output: Path):
    manifest = json.loads((ROOT / "browser-extension/manifest.json").read_text(encoding="utf-8"))
    if manifest["permissions"] != ["activeTab", "nativeMessaging"]:
        raise ValueError("Unexpected browser permissions")
    if "host_permissions" in manifest or "content_scripts" in manifest:
        raise ValueError("Unexpected browser access")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        def add(name, data, executable=False):
            item = zipfile.ZipInfo(f"{ARCHIVE_ROOT}/{name}")
            item.create_system = 3
            item.external_attr = (0o100755 if executable else 0o100644) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, data)
        for name in PAYLOAD_FILES:
            add(f"extension/{name}", (ROOT / "browser-extension" / name).read_bytes())
        add("extension/icon.png", (ROOT / "buzz/assets/buzz-icon-1024.png").read_bytes())
        add("Install Buzz Extension.command", (ROOT / "browser-extension/setup/Install Buzz Extension.command").read_bytes(), executable=True)
        add("Quick Start.html", (ROOT / "browser-extension/setup/Quick Start.html").read_bytes())
        add("LICENSE", (ROOT / "LICENSE").read_bytes())
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    return {"path": str(output), "bytes": output.stat().st_size, "sha256": checksum, "extension_version": manifest["version"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/Buzz-Chrome-Setup-1.0.1-macOS.zip")
    print(json.dumps(package(parser.parse_args().output), indent=2))
