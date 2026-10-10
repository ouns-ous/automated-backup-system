"""
Tests for Dashboard and HTML Report generator.
"""

from pathlib import Path
import tempfile
import unittest

from automated_backup.config import BackupConfig
from automated_backup.dashboard import DashboardGenerator
from automated_backup.engine import BackupEngine


class TestDashboardGenerator(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

        self.source_dir = self.base_path / "source"
        self.backup_dir = self.base_path / "backups"
        self.source_dir.mkdir()
        self.backup_dir.mkdir()

        (self.source_dir / "note.txt").write_text("Hello Dashboard", encoding="utf-8")

        self.config = BackupConfig(
            task_name="dashboard_job",
            source_dirs=[str(self.source_dir)],
            backup_dest=str(self.backup_dir),
            compression="zip",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generate_html_and_markdown(self):
        engine = BackupEngine(self.config)
        engine.run_backup(force_full=True)

        generator = DashboardGenerator(self.config)
        html = generator.generate_html_report()
        md = generator.generate_markdown_report()

        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("ByteVault", html)
        self.assertIn("dashboard_job", html)

        self.assertIn("# ByteVault Status Report", md)
        self.assertIn("Total Recorded Snapshots", md)

        # Test export
        out_html = self.base_path / "report.html"
        generator.export(out_html, fmt="html")
        self.assertTrue(out_html.exists())
        self.assertGreater(out_html.stat().st_size, 100)


if __name__ == "__main__":
    unittest.main()
