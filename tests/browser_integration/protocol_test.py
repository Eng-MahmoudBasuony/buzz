import io
import json
import struct
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

pytest.importorskip("fcntl", reason="The macOS browser bridge requires POSIX file locks")

from buzz.browser_integration import EXTENSION_ID
from buzz.browser_integration.protocol import (
    Store, ORIGIN, canonical_video, read_frame, write_frame, atomic_json, public_status,
)
from buzz.browser_integration.host import run, handle

URL = "https://www.youtube.com/watch?v=abcdefghijk"


@pytest.mark.parametrize("url", [URL + "&t=100s", "https://youtu.be/abcdefghijk?t=15",
    "https://m.youtube.com/watch?v=abcdefghijk", "https://www.youtube.com/shorts/abcdefghijk",
    "https://www.youtube.com/live/abcdefghijk", "https://www.youtube.com/embed/abcdefghijk"])
def test_canonical_video(url):
    assert canonical_video(url) == ("abcdefghijk", URL)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://youtube.com/watch?v=abcdefghijk",
    "https://www.youtube.com.evil.example/watch?v=abcdefghijk", "https://youtube.com@evil.example/watch?v=abcdefghijk",
    "https://youtube.com:443/watch?v=abcdefghijk", "https://youtube.com/@channel", "https://youtube.com/playlist?list=abcdefghijk",
    "https://youtu.be/../../private", "https://youtu.be/abcdefghijk/extra", URL + ";$(touch example)", None, 123])
def test_rejects_non_video_or_untrusted_input(url):
    with pytest.raises(ValueError):
        canonical_video(url)


def test_duplicate_clicks_share_one_record_even_concurrently(tmp_path):
    store = Store(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = list(pool.map(lambda _: store.start(URL), range(20)))
    assert {job["id"] for job in jobs} == {"abcdefghijk"}
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert store.path("abcdefghijk").stat().st_mode & 0o777 == 0o600
    assert tmp_path.stat().st_mode & 0o777 == 0o700


def test_failure_requires_an_explicit_retry(tmp_path):
    store = Store(tmp_path)
    job = store.start(URL)
    job.update(state="failed", task_uid="old-task")
    store.save(job)
    assert store.start(URL)["task_uid"] == "old-task"
    retried = store.start(URL, retry=True)
    assert retried["state"] == "waiting"
    assert "task_uid" not in retried


def test_completed_job_is_reopened_instead_of_resubmitted(tmp_path):
    store = Store(tmp_path)
    job = store.start(URL)
    job.update(state="completed", task_uid="finished", open_requested=False)
    store.save(job)
    assert store.start(URL + "&t=22")["task_uid"] == "finished"
    assert store.read("abcdefghijk")["open_requested"] is True


def test_skipped_job_is_reopened_instead_of_resubmitted(tmp_path):
    store = Store(tmp_path)
    job = store.start(URL)
    job.update(state="skipped", task_uid="finished", open_requested=False)
    store.save(job)
    reopened = store.start(URL)
    assert reopened["task_uid"] == "finished"
    assert reopened["open_requested"] is True


def test_status_never_exposes_credentials_paths_or_raw_api_response():
    public = public_status({"id": "abcdefghijk", "state": "completed", "api_key": "fixture-secret",
        "options": {"openai_access_token": "fixture-secret"}, "path": "/private/file", "response": "raw"})
    assert public == {"id": "abcdefghijk", "state": "completed"}


def test_rejects_symlinked_job_and_path_traversal(tmp_path):
    store = Store(tmp_path / "bridge")
    external = tmp_path / "other.json"
    external.write_text('{}')
    store.path("abcdefghijk").symlink_to(external)
    with pytest.raises(OSError):
        store.read("abcdefghijk")
    with pytest.raises(ValueError):
        store.path("../other")


def test_rejects_tampered_identity(tmp_path):
    store = Store(tmp_path)
    atomic_json(store.path("abcdefghijk"), {"id": "abcdefghijk", "url": "https://youtu.be/abcdefghijk"})
    with pytest.raises(ValueError):
        store.read("abcdefghijk")


def test_frame_uses_utf8_byte_length_and_multiple_messages():
    stream = io.BytesIO()
    write_frame(stream, {"message": "نص عربي"})
    write_frame(stream, {"next": True})
    stream.seek(0)
    assert read_frame(stream) == {"message": "نص عربي"}
    assert read_frame(stream) == {"next": True}
    assert read_frame(stream) is None


@pytest.mark.parametrize("data", [b"x", struct.pack("=I", 65537), struct.pack("=I", 3) + b"{}", struct.pack("=I", 2) + b"[]"])
def test_invalid_frame_is_rejected(data):
    with pytest.raises((ValueError, json.JSONDecodeError)):
        read_frame(io.BytesIO(data))


def test_unapproved_origin_cannot_start_app_or_create_queue(tmp_path):
    destination = io.BytesIO()
    assert run("chrome-extension://not-allowed/", io.BytesIO(), destination) == 1
    destination.seek(0)
    assert read_frame(destination)["ok"] is False


def test_host_protocol_enqueues_and_reads_status_without_credentials(tmp_path):
    store = Store(tmp_path)
    atomic_json(tmp_path / "enabled.json", {"enabled": True, "origin": ORIGIN})
    launches = []
    source = io.BytesIO()
    write_frame(source, {"action": "start", "url": URL})
    write_frame(source, {"action": "status", "id": "abcdefghijk"})
    source.seek(0)
    destination = io.BytesIO()
    assert run(ORIGIN, source, destination, store, lambda: launches.append(True)) == 0
    destination.seek(0)
    assert read_frame(destination)["job"]["state"] == "waiting"
    assert read_frame(destination)["job"]["id"] == "abcdefghijk"
    assert launches == [True]
    assert "token" not in (tmp_path / "abcdefghijk.json").read_text()


def test_disabled_bridge_and_arbitrary_commands_cannot_launch(tmp_path):
    store = Store(tmp_path)
    atomic_json(tmp_path / "enabled.json", {"enabled": False, "origin": ORIGIN})
    with pytest.raises(ValueError):
        handle({"action": "start", "url": URL}, store, lambda: pytest.fail("unexpected launch"))
    atomic_json(tmp_path / "enabled.json", {"enabled": True, "origin": ORIGIN})
    with pytest.raises(ValueError):
        handle({"action": "exec", "command": "whoami"}, store, lambda: pytest.fail("unexpected launch"))
    with pytest.raises(ValueError):
        handle({"action": "start", "url": URL, "api_key": "fixture-secret"}, store)


def test_manifest_identity_matches_native_host():
    import base64
    import hashlib
    manifest = json.loads((Path(__file__).parents[2] / "browser-extension/manifest.json").read_text())
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    assert ''.join(chr(ord('a') + int(n, 16)) for n in digest) == EXTENSION_ID
    assert manifest["permissions"] == ["activeTab", "nativeMessaging"]
    assert "host_permissions" not in manifest
    assert "content_scripts" not in manifest
