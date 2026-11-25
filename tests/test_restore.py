"""
Tests for Restore Engine (full snapshot restore, incremental chain restore, checksum verification).
"""

from pathlib import Path
import tempfile
import time
import unittest

from automated_backup.config import BackupConfig
from automated_backup.engine import BackupEngine
from automated_backup.restore import RestoreEngine


class TestRestoreEngine(unittest.TestCase):

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
            task_name="restore_job",
            source_dirs=[str(self.source_dir)],
            backup_dest=str(self.backup_dir),
            compression="zip",
            incremental=True,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_full_restore(self):
        # Create sample files
        (self.source_dir / "alpha.txt").write_text("Alpha content", encoding="utf-8")
        sub = self.source_dir / "nested"
        sub.mkdir()
        (sub / "beta.txt").write_text("Beta content", encoding="utf-8")

        engine = BackupEngine(self.config)
        backup_res = engine.run_backup(force_full=True)

        restore_engine = RestoreEngine(self.backup_dir)
        restore_res = restore_engine.restore(
            snapshot_id=backup_res["snapshot_id"],
            target_dir=self.restore_dir,
            verify_checksums=True
        )

        self.assertEqual(restore_res["status"], "success")
        self.assertEqual(restore_res["restored_files_count"], 2)
        self.assertEqual(restore_res["corrupted_files"], [])

        # Verify restored files on disk
        self.assertEqual((self.restore_dir / "alpha.txt").read_text(encoding="utf-8"), "Alpha content")
        self.assertEqual((self.restore_dir / "nested" / "beta.txt").read_text(encoding="utf-8"), "Beta content")

    def test_incremental_chain_restore(self):
        # Step 1: Base full backup
        (self.source_dir / "file1.txt").write_text("v1 of file1", encoding="utf-8")
        (self.source_dir / "file2.txt").write_text("v1 of file2", encoding="utf-8")

        engine = BackupEngine(self.config)
        snap1 = engine.run_backup()

        time.sleep(0.05)

        # Step 2: Incremental update
        # Modify file1, add file3
        (self.source_dir / "file1.txt").write_text("v2 of file1 updated", encoding="utf-8")
        (self.source_dir / "file3.txt").write_text("new file 3", encoding="utf-8")

        snap2 = engine.run_backup()
        self.assertEqual(snap2["type"], "inc")

        # Step 3: Restore incremental snapshot to empty target
        restore_target = self.base_path / "restore_inc"
        restore_engine = RestoreEngine(self.backup_dir)
        restore_res = restore_engine.restore(
            snapshot_id=snap2["snapshot_id"],
            target_dir=restore_target,
            verify_checksums=True
        )

        self.assertEqual(restore_res["status"], "success")
        self.assertEqual(restore_res["restored_files_count"], 3)
        self.assertEqual(restore_res["corrupted_files"], [])

        # Check reconstructed states:
        # file1 has v2 content
        self.assertEqual((restore_target / "file1.txt").read_text(encoding="utf-8"), "v2 of file1 updated")
        # file2 has v1 content (from base snapshot)
        self.assertEqual((restore_target / "file2.txt").read_text(encoding="utf-8"), "v1 of file2")
        # file3 has new content
        self.assertEqual((restore_target / "file3.txt").read_text(encoding="utf-8"), "new file 3")

    def test_selective_restore_dry_run_and_skip_existing(self):
        (self.source_dir / "keep.py").write_text("print('keep')", encoding="utf-8")
        (self.source_dir / "ignore.log").write_text("log data", encoding="utf-8")
        (self.source_dir / "notes.md").write_text("# Notes", encoding="utf-8")

        engine = BackupEngine(self.config)
        snap = engine.run_backup(force_full=True)
        restore_engine = RestoreEngine(self.backup_dir)

        # Dry run with include/exclude
        dry = restore_engine.restore(
            snapshot_id=snap["snapshot_id"],
            target_dir=self.restore_dir,
            include_patterns=["*.py", "*.md"],
            exclude_patterns=["*.md"],
            dry_run=True,
        )
        self.assertEqual(dry["status"], "dry_run")
        self.assertEqual(dry["planned_files"], ["keep.py"])
        self.assertFalse((self.restore_dir / "keep.py").exists())

        # Pre-populate keep.py and restore with overwrite=False
        (self.restore_dir / "keep.py").write_text("existing custom", encoding="utf-8")
        res = restore_engine.restore(
            snapshot_id=snap["snapshot_id"],
            target_dir=self.restore_dir,
            include_patterns=["*.py", "*.md"],
            overwrite=False,
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["skipped_count"], 1)
        self.assertEqual(res["restored_files_count"], 1)
        self.assertEqual((self.restore_dir / "keep.py").read_text(encoding="utf-8"), "existing custom")
        self.assertEqual((self.restore_dir / "notes.md").read_text(encoding="utf-8"), "# Notes")
        self.assertFalse((self.restore_dir / "ignore.log").exists())

    def test_safe_target_path_blocks_traversal(self):
        with self.assertRaises(ValueError):
            RestoreEngine._safe_target_path(self.restore_dir.resolve(), "../outside.txt")


if __name__ == "__main__":
    unittest.main()
