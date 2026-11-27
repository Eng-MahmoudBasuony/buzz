"""Cloud transcription preparation, checkpoints, and quality checks.

This module has no model/GPU imports. Repetition detection is a heuristic,
not a guarantee of transcript accuracy. It never retries paid requests.
"""

import collections
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlparse
from platformdirs import user_cache_dir

LOG = logging.getLogger(__name__)
ROOT = Path(user_cache_dir("Buzz")) / "cloud-transcription"
STAGES = {}
VERSION = "1"


def stage(self, label, progress):
    STAGES[str(self.transcription_task.uid)] = label
    self.progress.emit((round(max(0, min(progress, 1)) * 10000), 10000))


def url_key(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        video = (
            parsed.path.lstrip("/")
            if host == "youtu.be"
            else parse_qs(parsed.query).get("v", [""])[0]
        )
        if video:
            url = "youtube:" + video
    return hashlib.sha256(url.encode()).hexdigest()[:24]


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        json.dump(data, stream, ensure_ascii=False)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def cached_audio(url):
    folder = ROOT / "audio" / url_key(url)
    try:
        data = json.loads((folder / "source.json").read_text())
        path = (folder / data["name"]).resolve()
        if (
            path.parent == folder.resolve()
            and path.is_file()
            and path.stat().st_size > 44
        ):
            return path
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def preserve_audio(url, source, display_name=None):
    source = Path(source)
    folder = ROOT / "audio" / url_key(url)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / source.name
    if target.resolve() != source.resolve():
        with tempfile.NamedTemporaryFile(
            dir=folder, suffix=".wav", delete=False
        ) as stream:
            temporary = Path(stream.name)
        try:
            shutil.copyfile(source, temporary)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    atomic_json(
        folder / "source.json",
        {"url": url, "name": target.name, "display_name": display_name},
    )
    return target


def tool(name):
    import sys

    bundled = Path(getattr(sys, "_MEIPASS", "")) / name
    return str(bundled) if bundled.is_file() else shutil.which(name) or name


def run_media(arguments, timeout=180):
    kwargs = {}
    if sys.platform == "win32":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs = {"startupinfo": startup, "creationflags": subprocess.CREATE_NO_WINDOW}
    result = subprocess.run(
        arguments, capture_output=True, text=True, timeout=timeout, **kwargs
    )
    if result.returncode:
        raise RuntimeError("Audio preparation failed: " + result.stderr[-500:])
    return result


def duration(path):
    result = run_media(
        [
            tool("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        30,
    )
    value = float(json.loads(result.stdout)["format"]["duration"])
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError("The audio has no valid duration.")
    return value


def pauses(path, seconds):
    # Only choose chunk boundaries; never remove quiet speech or change offsets.
    result = run_media(
        [
            tool("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-i",
            str(path),
            "-af",
            "silencedetect=noise=-50dB:d=0.5",
            "-f",
            "null",
            "-",
        ],
        max(180, seconds / 8),
    )
    points = []
    beginning = None
    for line in result.stderr.splitlines():
        start = re.search(r"silence_start: ([\d.]+)", line)
        end = re.search(r"silence_end: ([\d.]+)", line)
        if start:
            beginning = float(start.group(1))
        if end and beginning is not None:
            points.append((beginning + float(end.group(1))) / 2)
            beginning = None
    return points


def chunk_ranges(seconds, boundaries):
    chunks = []
    start = 0.0
    while start < seconds - 0.001:
        target = min(seconds, start + (60 if not chunks else 180))
        candidates = [
            p for p in boundaries if target - 15 <= p <= target and p > start + 20
        ]
        end = max(candidates) if candidates and target < seconds else target
        chunks.append((start, end))
        start = end
    return chunks


def normalized_text(text):
    return " ".join(re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE))


def validate_segments(segments):
    texts = [normalized_text(s.text) for s in segments if normalized_text(s.text)]
    if len(texts) >= 5:
        _, count = collections.Counter(texts).most_common(1)[0]
        if count >= 5 and count / len(texts) >= 0.75:
            raise RuntimeError(
                "Transcription quality check failed: repeated text. Processing stopped; no automatic paid retry."
            )
    words = " ".join(texts).split()
    for width in range(3, min(13, len(words) // 6 + 1)):
        for start in range(len(words) - width * 6 + 1):
            phrase = words[start : start + width]
            if all(
                words[start + repeat * width : start + (repeat + 1) * width] == phrase
                for repeat in range(1, 6)
            ):
                raise RuntimeError(
                    "Transcription quality check failed: a phrase repeats continuously. Review the audio before retrying."
                )


def get_value(value, name, default=None):
    return (
        value.get(name, default)
        if isinstance(value, dict)
        else getattr(value, name, default)
    )


def request_chunk(self, path, offset, seconds):
    from buzz.transcriber.transcriber import Segment

    options = self.transcription_task.transcription_options
    model = self.whisper_api_model
    request = {"model": model}
    prompt = options.initial_prompt.strip()
    if prompt:
        request["prompt"] = prompt
    if model == "gpt-transcribe":
        if options.language:
            request["extra_body"] = {"languages": [options.language]}
    else:
        request["response_format"] = "verbose_json" if model == "whisper-1" else "json"
        if options.language:
            request["language"] = options.language
        request["temperature"] = 0
        if self.word_level_timings:
            request["timestamp_granularities"] = ["word"]
    client = self.openai_client.with_options(timeout=120.0, max_retries=0)
    with open(path, "rb") as stream:
        response = client.audio.transcriptions.create(file=stream, **request)
    raw = get_value(response, "words" if self.word_level_timings else "segments")
    if raw is None:
        text = get_value(response, "text", "").strip()
        raw = [{"start": 0, "end": seconds, "text": text}] if text else []
    result = []
    for item in raw:
        text = get_value(
            item, "word" if self.word_level_timings else "text", ""
        ).strip()
        if not text:
            continue
        start = max(0, min(seconds, float(get_value(item, "start", 0))))
        end = max(start, min(seconds, float(get_value(item, "end", seconds))))
        result.append(
            Segment(
                start=round((offset + start) * 1000),
                end=round((offset + end) * 1000),
                text=text,
            )
        )
    self.api_responses.append({"offset_ms": round(offset * 1000), "response": response})
    validate_segments(result)
    return result


def reliable_transcribe(self):
    from buzz.transcriber.transcriber import Segment, Task

    if self.task != Task.TRANSCRIBE:
        return self._legacy_transcribe()
    model = self.whisper_api_model
    if model not in {
        "whisper-1",
        "gpt-transcribe",
        "gpt-4o-transcribe",
        "gpt-4o-mini-transcribe",
    }:
        return self._legacy_transcribe()
    options = self.transcription_task.transcription_options
    formats = self.transcription_task.file_transcription_options.output_formats
    if model != "whisper-1" and (
        self.word_level_timings
        or any(getattr(f, "value", f) in {"srt", "vtt"} for f in formats)
    ):
        raise RuntimeError(
            "This model returns text without precise timestamps. Select TXT only, or use whisper-1 for SRT/VTT and word timings."
        )
    source = Path(self.transcription_task.file_path)
    stage(self, "Checking audio", 0.21)
    seconds = duration(source)
    ranges = chunk_ranges(seconds, pauses(source, seconds))
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    config = [
        VERSION,
        model,
        options.language,
        options.initial_prompt,
        self.word_level_timings,
        ranges,
    ]
    digest.update(json.dumps(config, sort_keys=True).encode())
    checkpoint_dir = ROOT / "checkpoints" / digest.hexdigest()[:32]
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    segments = []
    for index, (start, end) in enumerate(ranges):
        checkpoint = checkpoint_dir / f"{index:04}.json"
        current = None
        if checkpoint.exists():
            try:
                saved = json.loads(checkpoint.read_text())
                current = [Segment(**item) for item in saved["segments"]]
                validate_segments(current)
                self.api_responses.append(saved["api_response"])
            except (OSError, ValueError, TypeError, RuntimeError, KeyError):
                current = None
        if current is None:
            stage(
                self,
                f"Preparing audio {index + 1}/{len(ranges)}",
                0.22 + 0.77 * start / seconds,
            )
            with tempfile.TemporaryDirectory(prefix="buzz-url-fix-") as folder:
                chunk = Path(folder) / "speech.wav"
                # Lossless PCM, normalized loudness with a true-peak limit.
                run_media(
                    [
                        tool("ffmpeg"),
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-nostdin",
                        "-ss",
                        str(start),
                        "-i",
                        str(source),
                        "-t",
                        str(end - start),
                        "-af",
                        "loudnorm=I=-18:TP=-2:LRA=11",
                        "-ar",
                        "16000",
                        "-ac",
                        "1",
                        "-c:a",
                        "pcm_s16le",
                        str(chunk),
                    ]
                )
                if chunk.stat().st_size >= 25 * 1024 * 1024:
                    raise RuntimeError(
                        "Prepared audio chunk exceeds the API upload limit."
                    )
                stage(
                    self,
                    f"Transcribing {index + 1}/{len(ranges)} — waiting for OpenAI",
                    0.22 + 0.77 * start / seconds,
                )
                current = request_chunk(self, chunk, start, end - start)
            response = self.api_responses[-1]["response"]
            metadata = (
                response.model_dump(mode="json")
                if hasattr(response, "model_dump")
                else vars(response)
            )
            atomic_json(
                checkpoint,
                {
                    "segments": [
                        dict(start=s.start, end=s.end, text=s.text) for s in current
                    ],
                    "api_response": {
                        "offset_ms": round(start * 1000),
                        "response": metadata,
                    },
                },
            )
        segments.extend(current)
        validate_segments(segments)
        stage(
            self, f"Transcribed {index + 1}/{len(ranges)}", 0.22 + 0.77 * end / seconds
        )
    if not segments:
        raise RuntimeError(
            "No speech was recognized. Check the audio before another paid attempt."
        )
    stage(self, "Transcription checked; saving", 1)
    LOG.info(
        "Transcription passed repetition checks (%s chunks, %s segments)",
        len(ranges),
        len(segments),
    )
    return segments
