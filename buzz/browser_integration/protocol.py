"""Small local queue shared by the Chrome host and the GUI. No credentials."""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import struct
import tempfile
import time

from buzz.browser_integration import EXTENSION_ID
from buzz.youtube_url import VIDEO_ID, canonical_video

ORIGIN = f"chrome-extension://{EXTENSION_ID}/"
MAX_MESSAGE = 65536


def bridge_root():
    from platformdirs import user_data_dir
    return Path(user_data_dir("Buzz")) / "browser-bridge"


def read_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or info.st_size > MAX_MESSAGE:
            raise ValueError("Invalid local bridge file")
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = -1
            value = json.load(stream)
        if not isinstance(value, dict):
            raise ValueError("Invalid local bridge record")
        return value
    finally:
        if fd != -1:
            os.close(fd)


def atomic_json(path, value):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, ensure_ascii=False)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Store:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else bridge_root()
        if self.root.is_symlink():
            raise ValueError("Invalid bridge directory")
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.root.stat().st_uid != os.getuid():
            raise ValueError("Invalid bridge directory owner")
        self.root.chmod(0o700)

    @contextlib.contextmanager
    def locked(self):
        fd = os.open(self.root / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def path(self, video):
        if not isinstance(video, str) or not VIDEO_ID.fullmatch(video):
            raise ValueError("Invalid video ID")
        return self.root / (video + ".json")

    def read(self, video):
        value = read_json(self.path(video))
        expected, url = canonical_video(value.get("url"))
        if expected != video or value.get("id") != video or value["url"] != url:
            raise ValueError("Invalid job identity")
        return value

    def save(self, value):
        atomic_json(self.path(value["id"]), value)

    def start(self, url, retry=False):
        video, url = canonical_video(url)
        with self.locked():
            try:
                job = self.read(video)
            except FileNotFoundError:
                job = None
            if job is None or (retry and job.get("state") in {"failed", "canceled", "missing"}):
                job = {"id": video, "url": url, "state": "waiting", "progress": 0,
                       "created": time.time(), "open_requested": True}
            elif job.get("state") in {"completed", "skipped"}:
                job["open_requested"] = True
            self.save(job)
        return job


def public_status(job):
    # Never send task options, API responses, keys, paths, or exception details.
    return {key: job[key] for key in ("id", "url", "state", "progress", "stage", "message") if key in job}


def read_frame(stream):
    header = stream.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise ValueError("Truncated native message")
    size = struct.unpack("=I", header)[0]
    if size < 2 or size > MAX_MESSAGE:
        raise ValueError("Invalid native message size")
    data = bytearray()
    while len(data) < size:
        part = stream.read(size - len(data))
        if not part:
            raise ValueError("Truncated native message")
        data.extend(part)
    message = json.loads(data)
    if not isinstance(message, dict):
        raise ValueError("Invalid native message")
    return message


def write_frame(stream, message):
    data = json.dumps(message, ensure_ascii=False).encode("utf-8")
    if len(data) > MAX_MESSAGE:
        raise ValueError("Native response too large")
    stream.write(struct.pack("=I", len(data)) + data)
    stream.flush()
