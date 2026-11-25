"""
Tests for File History Engine and Duplicate Analyzer.
"""

from pathlib import Path
import tempfile
import time
import unittest

from automated_backup.config import BackupConfig
from automated_backup.engine import BackupEngine
from automated_backup.history import FileHistoryEngine


class TestFileHistoryEngine(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

        self.source_dir = self.base_path / "source"
        self.backup_dir = self.base_path / "backups"
        self.restore_dir = self.base_path / "restored"
        self.source_dir.mkdir()
        self.backup_dir.mkdir()
        self.restore_dir.mkdir()

        self.config = BackupConfig(
            task_name="history_job",
            source_dirs=[str(self.source_dir)],
            backup_dest=str(self.backup_dir),
            compression="zip",
            incremental=True,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_file_revision_timeline_and_single_file_restore(self):
        engine = BackupEngine(self.config)

        # Snapshot 1: Add app.py and readme.md
        (self.source_dir / "app.py").write_text("version = 1", encoding="utf-8")
        (self.source_dir / "readme.md").write_text("docs", encoding="utf-8")
        snap1 = engine.run_backup(force_full=True)
        time.sleep(1.05)

        # Snapshot 2: Modify app.py, keep readme.md unchanged
        (self.source_dir / "app.py").write_text("version = 2", encoding="utf-8")
        snap2 = engine.run_backup()
        time.sleep(1.05)

        # Snapshot 3: Delete app.py
        (self.source_dir / "app.py").unlink()
        snap3 = engine.run_backup()

        hist_engine = FileHistoryEngine(self.config)
        full_hist = hist_engine.get_file_history("app.py", changes_only=False)
        self.assertEqual(full_hist["matched_files_count"], 1)
        timeline = full_hist["files"]["app.py"]
        self.assertEqual([e["status"] for e in timeline], ["ADDED", "MODIFIED", "DELETED"])

        # Test changes_only on readme.md (ADDED then UNCHANGED x2 -> only 1 entry)
        readme_hist = hist_engine.get_file_history("readme.md", changes_only=True)
        self.assertEqual(len(readme_hist["files"]["readme.md"]), 1)
        self.assertEqual(readme_hist["files"]["readme.md"][0]["status"], "ADDED")

        # Point-in-time single-file restore from snap1
        res = hist_engine.restore_file_version(
            file_path="app.py",
            snapshot_id=snap1["snapshot_id"],
            target_dir=self.restore_dir,
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual((self.restore_dir / "app.py").read_text(encoding="utf-8"), "version = 1")
        self.assertFalse((self.restore_dir / "readme.md").exists())
        self.assertNotEqual(snap2["snapshot_id"], snap3["snapshot_id"])

    def test_find_duplicate_files(self):
        payload = "identical content repeated across files"
        (self.source_dir / "dup1.txt").write_text(payload, encoding="utf-8")
        (self.source_dir / "dup2.txt").write_text(payload, encoding="utf-8")
        (self.source_dir / "unique.txt").write_text("something else", encoding="utf-8")

        engine = BackupEngine(self.config)
        engine.run_backup(force_full=True)

        hist_engine = FileHistoryEngine(self.config)
        dup = hist_engine.find_duplicate_files("latest")

        self.assertEqual(dup["duplicate_groups_count"], 1)
        self.assertEqual(dup["total_duplicate_files"], 2)
        self.assertEqual(dup["wasted_bytes"], len(payload.encode("utf-8")))
        self.assertEqual(sorted(dup["groups"][0]["paths"]), ["dup1.txt", "dup2.txt"])


if __name__ == "__main__":
    unittest.main()
