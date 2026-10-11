import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(
    shutil.which("espeak-ng") and shutil.which("ffmpeg"),
    "CI installs espeak-ng and FFmpeg for the real Whisper smoke test",
)
class WhisperRuntimeSmokeTests(unittest.TestCase):
    def test_local_whisper_transcribes_a_generated_speech_fixture(self):
        from ocular_audio_mcp import _blocking_whisper_transcription

        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "known-speech.wav"
            subprocess.run(
                [
                    "espeak-ng",
                    "-s",
                    "135",
                    "-w",
                    str(audio_path),
                    "The quarterly revenue increased by forty two percent.",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            transcript = _blocking_whisper_transcription(str(audio_path), "")
            self.assertTrue(transcript.strip(), "Whisper returned an empty transcript for speech audio")


if __name__ == "__main__":
    unittest.main()
