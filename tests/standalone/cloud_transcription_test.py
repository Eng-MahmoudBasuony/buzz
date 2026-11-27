"""Offline regression checks. Run with uv and platformdirs; no API calls.

The two dataclass/enum contracts below isolate preparation/request handling
from GPU and Qt imports. Full application integration needs the normal suite.
"""

import sys
import tempfile
import unittest
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@dataclass
class Segment:
    start: int
    end: int
    text: str


class Task(Enum):
    TRANSCRIBE = "transcribe"
    TRANSLATE = "translate"


contracts = ModuleType("buzz.transcriber.transcriber")
contracts.Segment, contracts.Task = Segment, Task
from buzz.transcriber import cloud_transcription as repair


class Signal:
    def __init__(self):
        self.values = []

    def emit(self, value):
        self.values.append(value)


def worker():
    return SimpleNamespace(
        transcription_task=SimpleNamespace(
            uid="sample",
            url="https://youtube.com/watch?v=sample",
            transcription_options=SimpleNamespace(language="ar", initial_prompt=""),
        ),
        progress=Signal(),
        download_progress=Signal(),
        error=Signal(),
    )


class RegressionTests(unittest.TestCase):
    def setUp(self):
        module_patch = patch.dict(sys.modules, {contracts.__name__: contracts})
        module_patch.start()
        self.addCleanup(module_patch.stop)
        stage_patch = patch.dict(repair.STAGES, clear=True)
        stage_patch.start()
        self.addCleanup(stage_patch.stop)

    def test_observed_failed_result_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "repeated text"):
            repair.validate_segments(
                [
                    Segment(
                        i * 30000,
                        i * 30000 + 4000,
                        "المترجم الى اللقاء في الفيديو الاخير",
                    )
                    for i in range(163)
                ]
            )

    def test_repetition_in_one_response_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "repeats continuously"):
            repair.validate_segments([Segment(0, 1000, "هذه جملة مكررة " * 10)])

    def test_normal_speech_is_accepted(self):
        repair.validate_segments(
            [
                Segment(0, 1000, "نراجع برنامج تسجيل الدخول"),
                Segment(1000, 2000, "ثم نختبر التعامل مع الأخطاء"),
            ]
        )

    def test_ranges_cover_every_sample_without_gaps(self):
        chunks = repair.chunk_ranges(4892.00325, [55, 230, 408, 586])
        self.assertEqual(chunks[0], (0.0, 55))
        self.assertEqual(chunks[-1][1], 4892.00325)
        self.assertTrue(all(a[1] == b[0] for a, b in zip(chunks, chunks[1:])))
        self.assertTrue(all(0 < b - a <= 180 for a, b in chunks))

    def test_timestamp_parameter_does_not_change_video_identity(self):
        self.assertEqual(
            repair.url_key("https://www.youtube.com/watch?v=sample&t=399s"),
            repair.url_key("https://youtu.be/sample"),
        )

    def test_cache_rejects_paths_outside_its_folder(self):
        old = repair.ROOT
        with tempfile.TemporaryDirectory() as folder:
            repair.ROOT = Path(folder)
            try:
                repair.atomic_json(
                    repair.ROOT / "audio" / repair.url_key("test") / "source.json",
                    {"name": "../../outside.wav"},
                )
                self.assertIsNone(repair.cached_audio("test"))
            finally:
                repair.ROOT = old

    def test_current_model_request_and_text_timing(self):
        obj = worker()
        received = {}

        def create(**kw):
            received.update(kw)
            return SimpleNamespace(text="هذه تجربة تحويل الصوت إلى نص")

        obj.api_responses = []
        obj.whisper_api_model = "gpt-transcribe"
        obj.word_level_timings = False
        obj.openai_client = SimpleNamespace(
            with_options=lambda **kw: SimpleNamespace(
                audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))
            )
        )
        with tempfile.NamedTemporaryFile() as sample:
            result = repair.request_chunk(obj, sample.name, 60, 30)
        self.assertEqual(received["extra_body"], {"languages": ["ar"]})
        self.assertNotIn("language", received)
        self.assertNotIn("response_format", received)
        self.assertEqual((result[0].start, result[0].end), (60000, 90000))

    def test_legacy_timestamps_are_clamped_to_chunk(self):
        obj = worker()
        obj.api_responses = []
        obj.whisper_api_model = "whisper-1"
        obj.word_level_timings = False

        def create(**kw):
            return SimpleNamespace(
                segments=[{"start": -1, "end": 35, "text": "تجربة صحيحة"}]
            )

        obj.openai_client = SimpleNamespace(
            with_options=lambda **kw: SimpleNamespace(
                audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))
            )
        )
        with tempfile.NamedTemporaryFile() as sample:
            result = repair.request_chunk(obj, sample.name, 60, 30)
        self.assertEqual((result[0].start, result[0].end), (60000, 90000))

    def test_real_audio_pipeline_chunks_and_resumes_without_new_requests(self):
        old = repair.ROOT
        with tempfile.TemporaryDirectory() as folder:
            repair.ROOT = Path(folder) / "cache"
            try:
                source = Path(folder) / "quiet.wav"
                subprocess.run(
                    [
                        repair.tool("ffmpeg"),
                        "-v",
                        "error",
                        "-f",
                        "lavfi",
                        "-i",
                        "sine=frequency=440:duration=65",
                        "-af",
                        "volume=-30dB",
                        "-ar",
                        "16000",
                        "-ac",
                        "1",
                        str(source),
                    ],
                    check=True,
                )
                obj = worker()
                obj.api_responses = []
                obj.whisper_api_model = "gpt-transcribe"
                obj.word_level_timings = False
                obj.task = Task.TRANSCRIBE
                obj.transcription_task.file_path = str(source)
                obj.transcription_task.file_transcription_options = SimpleNamespace(
                    output_formats={"txt"}
                )
                calls = []

                def create(**kw):
                    calls.append(kw["file"].name)
                    return SimpleNamespace(
                        text="كلام تجريبي مختلف رقم " + str(len(calls))
                    )

                obj.openai_client = SimpleNamespace(
                    with_options=lambda **kw: SimpleNamespace(
                        audio=SimpleNamespace(
                            transcriptions=SimpleNamespace(create=create)
                        )
                    )
                )
                result = repair.reliable_transcribe(obj)
                self.assertEqual(len(calls), 2)
                self.assertEqual(
                    [(s.start, s.end) for s in result], [(0, 60000), (60000, 65000)]
                )
                obj.api_responses = []
                self.assertEqual(repair.reliable_transcribe(obj), result)
                self.assertEqual(
                    len(calls), 2, "resume must not send another billable request"
                )
                self.assertEqual(len(obj.api_responses), 2)
                self.assertEqual(obj.progress.values[-1], (10000, 10000))
            finally:
                repair.ROOT = old

    def test_saved_audio_roundtrip_keeps_display_name(self):
        old = repair.ROOT
        with tempfile.TemporaryDirectory() as folder:
            repair.ROOT = Path(folder) / "cache"
            try:
                source = Path(folder) / "audio.wav"
                source.write_bytes(b"sample" * 20)
                saved = repair.preserve_audio(
                    "https://youtube.com/watch?v=sample", source, "A video title"
                )
                self.assertTrue(
                    repair.cached_audio("https://youtu.be/sample").samefile(saved)
                )
                self.assertEqual(saved.read_bytes(), source.read_bytes())
                import json

                self.assertEqual(
                    json.loads((saved.parent / "source.json").read_text())[
                        "display_name"
                    ],
                    "A video title",
                )
            finally:
                repair.ROOT = old

    def test_timeout_is_not_retried(self):
        obj = worker()
        obj.api_responses = []
        obj.whisper_api_model = "gpt-transcribe"
        obj.word_level_timings = False
        calls = []
        client_options = []

        def create(**kwargs):
            calls.append(1)
            raise TimeoutError("server did not respond")

        def configured(**kwargs):
            client_options.append(kwargs)
            return SimpleNamespace(
                audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))
            )

        obj.openai_client = SimpleNamespace(with_options=configured)
        with tempfile.NamedTemporaryFile() as audio:
            with self.assertRaises(TimeoutError):
                repair.request_chunk(obj, audio.name, 0, 10)
        self.assertEqual(calls, [1])
        self.assertEqual(client_options[0]["max_retries"], 0)
        self.assertLessEqual(client_options[0]["timeout"], 120)

    def test_text_only_model_rejects_subtitles_before_any_request(self):
        obj = worker()
        obj.task = Task.TRANSCRIBE
        obj.whisper_api_model = "gpt-transcribe"
        obj.word_level_timings = False
        obj.transcription_task.file_transcription_options = SimpleNamespace(
            output_formats={"srt"}
        )
        with self.assertRaisesRegex(RuntimeError, "precise timestamps"):
            repair.reliable_transcribe(obj)

    def test_custom_compatible_models_keep_legacy_path(self):
        obj = worker()
        obj.task = Task.TRANSCRIBE
        obj.whisper_api_model = "custom-provider-model"
        obj._legacy_transcribe = lambda: ["legacy result"]
        self.assertEqual(repair.reliable_transcribe(obj), ["legacy result"])

    def test_real_audio_pipeline_rejects_bad_response_before_checkpoint(self):
        old = repair.ROOT
        with tempfile.TemporaryDirectory() as folder:
            repair.ROOT = Path(folder) / "cache"
            try:
                source = Path(folder) / "speech.wav"
                subprocess.run(
                    [
                        repair.tool("ffmpeg"),
                        "-v",
                        "error",
                        "-f",
                        "lavfi",
                        "-i",
                        "sine=frequency=440:duration=5",
                        "-ar",
                        "16000",
                        "-ac",
                        "1",
                        str(source),
                    ],
                    check=True,
                )
                obj = worker()
                obj.api_responses = []
                obj.whisper_api_model = "whisper-1"
                obj.word_level_timings = False
                obj.task = Task.TRANSCRIBE
                obj.transcription_task.file_path = str(source)
                obj.transcription_task.file_transcription_options = SimpleNamespace(
                    output_formats={"txt"}
                )
                calls = []

                def create(**kw):
                    calls.append(1)
                    return SimpleNamespace(
                        segments=[
                            {"start": i, "end": i + 1, "text": "هذه جملة مكررة"}
                            for i in range(5)
                        ]
                    )

                obj.openai_client = SimpleNamespace(
                    with_options=lambda **kw: SimpleNamespace(
                        audio=SimpleNamespace(
                            transcriptions=SimpleNamespace(create=create)
                        )
                    )
                )
                with self.assertRaisesRegex(RuntimeError, "quality check failed"):
                    repair.reliable_transcribe(obj)
                self.assertEqual(len(calls), 1)
                self.assertEqual(list(repair.ROOT.rglob("*.json")), [])
            finally:
                repair.ROOT = old


if __name__ == "__main__":
    unittest.main(verbosity=2)
