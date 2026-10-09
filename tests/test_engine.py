"""
Tests for Backup Engine (full backup, incremental backup, verification, dry-run).
"""

from pathlib import Path
import tempfile
import time
import unittest

from automated_backup.config import BackupConfig
from automated_backup.engine import BackupEngine


class TestBackupEngine(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

        self.source_dir = self.base_path / "source"
        self.backup_dir = self.base_path / "backups"
        self.source_dir.mkdir()
        self.backup_dir.mkdir()

        # Seed source files
        (self.source_dir / "file1.txt").write_text("Hello file 1", encoding="utf-8")
        (self.source_dir / "file2.txt").write_text("Hello file 2", encoding="utf-8")

        self.config = BackupConfig(
            task_name="test_job",
            source_dirs=[str(self.source_dir)],
            backup_dest=str(self.backup_dir),
            compression="zip",
            incremental=True,
            exclude_patterns=["*.tmp"]
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_full_backup_creation_and_verification(self):
        engine = BackupEngine(self.config)
        res = engine.run_backup(force_full=True)

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["type"], "full")
        self.assertEqual(res["files_packed_count"], 2)

        # Check files exist
        archive = self.backup_dir / res["archive_name"]
        manifest = self.backup_dir / f"{res['snapshot_id']}.manifest.json"
        self.assertTrue(archive.exists())
        self.assertTrue(manifest.exists())

        # Verify integrity
        v_res = engine.verify_snapshot(res["snapshot_id"])
        self.assertTrue(v_res["valid"])
        self.assertEqual(v_res["archive_sha256"], res["archive_sha256"])

    def test_incremental_backup(self):
        engine = BackupEngine(self.config)

        # Initial full backup
        res1 = engine.run_backup()
        self.assertEqual(res1["type"], "full")

        # Give a moment for mtime resolution
        time.sleep(0.05)

        # Modify file1 and add file3
        (self.source_dir / "file1.txt").write_text("Modified file 1 content", encoding="utf-8")
        (self.source_dir / "file3.txt").write_text("Brand new file 3", encoding="utf-8")

        # Run incremental backup
        res2 = engine.run_backup()
        self.assertEqual(res2["type"], "inc")
        self.assertEqual(res2["base_snapshot_id"], res1["snapshot_id"])
        self.assertEqual(res2["files_packed_count"], 2)  # only file1 and file3 packed

        changes = res2["changes_summary"]
        self.assertEqual(changes["added"], 1)
        self.assertEqual(changes["modified"], 1)
        self.assertEqual(changes["unchanged"], 1)  # file2 untouched

        # Verify both snapshots
        self.assertTrue(engine.verify_snapshot(res1["snapshot_id"])["valid"])
        self.assertTrue(engine.verify_snapshot(res2["snapshot_id"])["valid"])

    def test_dry_run(self):
        engine = BackupEngine(self.config)
        res = engine.run_backup(dry_run=True)

        self.assertEqual(res["status"], "dry_run")
        self.assertEqual(res["files_to_pack_count"], 2)

        # Destination directory should remain empty of archives
        archives = list(self.backup_dir.glob("*.zip"))
        manifests = list(self.backup_dir.glob("*.manifest.json"))
        self.assertEqual(len(archives), 0)
        self.assertEqual(len(manifests), 0)


if __name__ == "__main__":
    unittest.main()
