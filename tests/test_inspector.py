"""
Tests for Snapshot Inspector and Diff Engine.
"""

from pathlib import Path
import tempfile
import time
import unittest

from automated_backup.config import BackupConfig
from automated_backup.engine import BackupEngine
from automated_backup.inspector import SnapshotInspector


class TestSnapshotInspector(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

        self.source_dir = self.base_path / "source"
        self.backup_dir = self.base_path / "backups"
        self.source_dir.mkdir()
        self.backup_dir.mkdir()

        (self.source_dir / "file1.txt").write_text("Hello file 1", encoding="utf-8")
        (self.source_dir / "file2.txt").write_text("Hello file 2", encoding="utf-8")

        self.config = BackupConfig(
            task_name="inspect_job",
            source_dirs=[str(self.source_dir)],
            backup_dest=str(self.backup_dir),
            compression="zip",
            incremental=True,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_inspect_snapshot(self):
        engine = BackupEngine(self.config)
        snap1 = engine.run_backup(force_full=True)

        inspector = SnapshotInspector(self.config)
        data = inspector.inspect_snapshot(snap1["snapshot_id"])

        self.assertEqual(data["snapshot_id"], snap1["snapshot_id"])
        self.assertEqual(data["files_count"], 2)
        paths = [f["path"] for f in data["files"]]
        self.assertIn("file1.txt", paths)
        self.assertIn("file2.txt", paths)

    def test_diff_snapshots_and_live(self):
        engine = BackupEngine(self.config)
        snap1 = engine.run_backup(force_full=True)

        time.sleep(0.05)
        # Modify file1, add file3
        (self.source_dir / "file1.txt").write_text("Updated file 1", encoding="utf-8")
        (self.source_dir / "file3.txt").write_text("Brand new file 3", encoding="utf-8")

        inspector = SnapshotInspector(self.config)

        # Live diff before running second backup
        live_diff = inspector.diff_live("latest")
        self.assertTrue(live_diff["has_changes"])
        self.assertIn("file3.txt", live_diff["added"])
        self.assertIn("file1.txt", live_diff["modified"])

        # Create second backup
        snap2 = engine.run_backup()

        # Diff between two snapshots
        diff = inspector.diff_snapshots(snap1["snapshot_id"], snap2["snapshot_id"])
        self.assertEqual(diff["added"], ["file3.txt"])
        self.assertEqual(diff["modified"], ["file1.txt"])
        self.assertEqual(diff["unchanged_count"], 1)  # file2 untouched


if __name__ == "__main__":
    unittest.main()
