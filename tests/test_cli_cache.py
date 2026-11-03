import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "cli.js"


@unittest.skipUnless(__import__("shutil").which("node"), "Node.js is required")
class CLICacheTests(unittest.TestCase):
    def test_clear_cache_removes_nested_evidence_visual_and_batch_data(self):
        with tempfile.TemporaryDirectory() as home:
            cache = Path(home) / ".cache" / "ocular_audio_mcp"
            fixtures = [
                cache / "video123.json",
                cache / "evidence" / "video123.json",
                cache / "visual" / "video123.json",
                cache / "visual" / "frames" / "video123" / "frame.jpg",
                cache / "batches" / "batch123.json",
                cache / "orphan.tmp",
                cache / "config.json",
                cache / "audit.jsonl",
                cache / "cookies.txt",
            ]
            for fixture in fixtures:
                fixture.parent.mkdir(parents=True, exist_ok=True)
                fixture.write_text("preserve" if fixture.name in {"config.json", "audit.jsonl", "cookies.txt"} else "cache", encoding="utf-8")

            env = {**os.environ, "HOME": home, "USERPROFILE": home}
            completed = subprocess.run(
                ["node", str(CLI), "--clear-cache"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(0, completed.returncode, msg=completed.stderr)
            for fixture in fixtures[:6]:
                self.assertFalse(fixture.exists(), msg=f"Cache artifact remains: {fixture}")
            for fixture in fixtures[6:]:
                self.assertTrue(fixture.exists(), msg=f"Non-cache data was deleted: {fixture}")


if __name__ == "__main__":
    unittest.main()
