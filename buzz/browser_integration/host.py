"""Chrome native messaging entry point. Does not import Qt or access keys."""
from pathlib import Path
import subprocess
import sys

from buzz.browser_integration.protocol import (
    ORIGIN, Store, public_status, read_frame, read_json, write_frame,
)


def launch_buzz():
    executable = Path(sys.executable).resolve()
    if executable.parent.name != "MacOS" or executable.parent.parent.name != "Contents":
        raise RuntimeError("The browser host must use the installed macOS Buzz app")
    app = executable.parent.parent.parent
    subprocess.run(["/usr/bin/open", "-g", "-a", str(app)], check=True, capture_output=True, timeout=15)


def handle(message, store, launch=launch_buzz):
    action = message.get("action")
    if action == "ping":
        return {"ok": True, "protocol": 1}
    config = read_json(store.root / "enabled.json")
    if config.get("enabled") is not True or config.get("origin") != ORIGIN:
        raise ValueError("وصلة المتصفح غير مفعلة. شغّل ملف الإعداد أولًا.")
    if action == "start":
        if set(message) - {"action", "url", "retry"} or type(message.get("retry", False)) is not bool:
            raise ValueError("Invalid start request")
        job = store.start(message.get("url"), message.get("retry", False))
        launch()
    elif action == "status":
        with store.locked():
            job = store.read(message.get("id"))
    else:
        raise ValueError("Invalid browser action")
    return {"ok": True, "job": public_status(job)}


def run(origin, source, destination, store=None, launch=launch_buzz):
    if origin != ORIGIN:
        write_frame(destination, {"ok": False, "message": "Browser extension is not allowed"})
        return 1
    store = store or Store()
    while True:
        try:
            message = read_frame(source)
            if message is None:
                return 0
            response = handle(message, store, launch)
        except (ValueError, FileNotFoundError):
            write_frame(destination, {"ok": False, "message": "تعذر قراءة طلب الإضافة. تأكد من الإعداد وصفحة الفيديو."})
            return 1
        except Exception:
            write_frame(destination, {"ok": False, "message": "تعذر الاتصال بـBuzz. افتحه وجرّب تاني."})
            return 1
        write_frame(destination, response)


def main():
    return run(sys.argv[1] if len(sys.argv) > 1 else "", sys.stdin.buffer, sys.stdout.buffer)
