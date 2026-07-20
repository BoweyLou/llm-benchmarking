from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from backend.versioning import project_root, read_app_version


class VersioningTests(unittest.TestCase):
    def test_repository_version_is_valid_semver(self) -> None:
        self.assertEqual(read_app_version(), "0.14.0")
        self.assertEqual(project_root() / "VERSION", Path(__file__).resolve().parents[1] / "VERSION")

    def test_reader_accepts_semver_and_rejects_invalid_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            version_file = Path(directory) / "VERSION"
            version_file.write_text("1.2.3-rc.1+build.5\n", encoding="utf-8")
            self.assertEqual(read_app_version(version_file), "1.2.3-rc.1+build.5")

            version_file.write_text("v1.2\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Invalid application VERSION"):
                read_app_version(version_file)
