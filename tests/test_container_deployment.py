from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ContainerDeploymentDefaultsTests(unittest.TestCase):
    def test_image_runs_as_dedicated_non_root_user(self):
        dockerfile = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("useradd --uid 10001 --gid 10001", dockerfile)
        self.assertIn("chown -R ocular:ocular /home/ocular/.cache", dockerfile)
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertIn("HOME=/home/ocular", dockerfile)

    def test_compose_binds_to_loopback_by_default(self):
        compose = (ROOT / "docker" / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn('"127.0.0.1:8000:8000"', compose)
        self.assertNotIn('"8000:8000"', compose)

    def test_compose_keeps_container_hardening(self):
        compose = (ROOT / "docker" / "docker-compose.yml").read_text(encoding="utf-8")
        for required in (
            "init: true",
            "pids_limit: 256",
            "read_only: true",
            "no-new-privileges:true",
            "cap_drop:",
            "- ALL",
            "/home/ocular/.cache/ocular_audio_mcp",
        ):
            with self.subTest(required=required):
                self.assertIn(required, compose)


if __name__ == "__main__":
    unittest.main()
