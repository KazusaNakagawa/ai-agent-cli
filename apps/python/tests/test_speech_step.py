"""The briefing's spoken script and optional audio (#517)."""
import subprocess
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.config import SpeechConfig
from src.notifier.speech import save_speech_script, synthesize_audio
from tests.generator.test_briefscript_notion import _full_doc


def _run_step(tmp_path, speech: SpeechConfig):
    from src.handler import step_speech

    ctx = MagicMock()
    ctx.results = {"generate": _full_doc()}
    with (
        patch("src.handler.CONFIG") as cfg,
        patch("src.handler.SPEECH_OUTPUT_DIR", tmp_path),
    ):
        cfg.speech = speech
        return step_speech(ctx)


class TestSpeechStep:
    def test_flag_off_writes_the_script_and_runs_no_tts(self, tmp_path):
        with patch("src.notifier.speech.subprocess.run") as run, \
             patch("src.notifier.speech.shutil.which") as which:
            result = _run_step(tmp_path, SpeechConfig())

        script = tmp_path / "briefing_2026-10-25.txt"
        assert result == {"script": str(script), "audio": None}
        assert script.read_text(encoding="utf-8").startswith("10月25日の")
        assert not list(tmp_path.glob("*.m4a"))
        run.assert_not_called()
        which.assert_not_called()

    def test_flag_on_without_the_engine_succeeds_and_warns(self, tmp_path, caplog):
        with patch("src.notifier.speech.shutil.which", return_value=None), \
             patch("src.notifier.speech.subprocess.run") as run:
            result = _run_step(tmp_path, SpeechConfig(audio=True))

        assert result["audio"] is None and result["script"]
        run.assert_not_called()
        assert any(r.levelname == "WARNING" and "say" in r.getMessage() for r in caplog.records)

    def test_flag_on_with_the_engine_returns_the_audio_path(self, tmp_path):
        with patch("src.notifier.speech.shutil.which", return_value="/usr/bin/say"), \
             patch("src.notifier.speech.subprocess.run") as run:
            result = _run_step(tmp_path, SpeechConfig(audio=True, voice="Kyoko"))

        assert result["audio"] == str(tmp_path / "briefing_2026-10-25.m4a")
        cmd = run.call_args.args[0]
        assert cmd[0] == "/usr/bin/say" and cmd[-2:] == ["-v", "Kyoko"]

    def test_max_chars_trims_the_script(self, tmp_path):
        result = _run_step(tmp_path, SpeechConfig(max_chars=40))
        assert len(open(result["script"], encoding="utf-8").read()) <= 40

    def test_script_write_failure_is_swallowed(self, tmp_path, caplog):
        with patch("src.handler.save_speech_script", side_effect=OSError("disk full")), \
             patch("src.notifier.speech.subprocess.run") as run:
            result = _run_step(tmp_path, SpeechConfig(audio=True))

        assert result == {"script": None, "audio": None}
        run.assert_not_called()
        assert any("speech script write failed" in r.getMessage() for r in caplog.records)


class TestSynthesizeAudio:
    @pytest.mark.parametrize("exc", [
        subprocess.CalledProcessError(1, "say"),
        subprocess.TimeoutExpired("say", 300),
        OSError("exec failed"),
    ])
    def test_engine_failure_returns_none(self, tmp_path, exc, caplog):
        script = save_speech_script("こんにちは。", tmp_path, date(2026, 10, 25))
        with patch("src.notifier.speech.shutil.which", return_value="/usr/bin/say"), \
             patch("src.notifier.speech.subprocess.run", side_effect=exc):
            assert synthesize_audio(script) is None
        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_no_voice_omits_the_flag(self, tmp_path):
        script = save_speech_script("こんにちは。", tmp_path, date(2026, 10, 25))
        with patch("src.notifier.speech.shutil.which", return_value="/usr/bin/say"), \
             patch("src.notifier.speech.subprocess.run") as run:
            synthesize_audio(script)
        assert "-v" not in run.call_args.args[0]


class TestSpeechConfig:
    def test_defaults_are_off(self):
        assert SpeechConfig() == SpeechConfig(audio=False, voice=None, max_chars=None)

    @pytest.mark.parametrize("bad", [{"max_chars": 0}, {"audo": True}])
    def test_invalid_values_are_rejected(self, bad):
        with pytest.raises(ValueError):
            SpeechConfig(**bad)
