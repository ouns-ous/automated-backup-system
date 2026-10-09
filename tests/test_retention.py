"""
Tests for Retention Manager.
"""

from pathlib import Path
import tempfile
import time
import unittest

from automated_backup.config import BackupConfig
from automated_backup.engine import BackupEngine
from automated_backup.retention import RetentionManager


class TestRetentionManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

        self.source_dir = self.base_path / "source"
        self.backup_dir = self.base_path / "backups"
        self.source_dir.mkdir()
        self.backup_dir.mkdir()

        (self.source_dir / "data.txt").write_text("sample data", encoding="utf-8")

        self.config = BackupConfig(
            task_name="retention_job",
            source_dirs=[str(self.source_dir)],
            backup_dest=str(self.backup_dir),
            retention_count=2,
            retention_days=None,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_prune_by_count(self):
        engine = BackupEngine(self.config)

        # Create 4 full snapshots
        sids = []
        for i in range(4):
            (self.source_dir / "data.txt").write_text(f"sample version {i}", encoding="utf-8")
            res = engine.run_backup(force_full=True)
            sids.append(res["snapshot_id"])
            time.sleep(1.05)  # ensure distinct timestamps

        retention = RetentionManager(self.config)
        all_snaps = retention.get_snapshots()
        self.assertEqual(len(all_snaps), 4)

        # Prune keeping 2
        prune_res = retention.prune_snapshots(retention_count=2)
        self.assertEqual(prune_res["pruned_count"], 2)
        self.assertEqual(prune_res["retained_count"], 2)
        self.assertIn(sids[0], prune_res["pruned_snapshots"])
        self.assertIn(sids[1], prune_res["pruned_snapshots"])

        # Remaining snapshots in folder
        remaining = retention.get_snapshots()
        self.assertEqual(len(remaining), 2)
        remaining_ids = [s["snapshot_id"] for s in remaining]
        self.assertEqual(remaining_ids, sids[2:])

    def test_prune_dry_run(self):
        engine = BackupEngine(self.config)
        for i in range(3):
            (self.source_dir / "data.txt").write_text(f"version {i}", encoding="utf-8")
            engine.run_backup(force_full=True)
            time.sleep(1.05)

        retention = RetentionManager(self.config)
        prune_res = retention.prune_snapshots(retention_count=1, dry_run=True)

        self.assertTrue(prune_res["dry_run"])
        self.assertEqual(prune_res["pruned_count"], 2)

        # Files should still exist
        all_snaps = retention.get_snapshots()
        self.assertEqual(len(all_snaps), 3)


if __name__ == "__main__":
    unittest.main()
