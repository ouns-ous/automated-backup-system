"""
Tests for BackupDoctor Diagnostics Engine.
"""

from pathlib import Path
import tempfile
import time
import unittest

from automated_backup.config import BackupConfig
from automated_backup.doctor import BackupDoctor
from automated_backup.engine import BackupEngine


class TestBackupDoctor(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

        self.source_dir = self.base_path / "source"
        self.backup_dir = self.base_path / "backups"
        self.source_dir.mkdir()
        self.backup_dir.mkdir()

        (self.source_dir / "a.txt").write_text("alpha", encoding="utf-8")
        (self.source_dir / "b.txt").write_text("beta", encoding="utf-8")

        self.config = BackupConfig(
            task_name="doctor_job",
            source_dirs=[str(self.source_dir)],
            backup_dest=str(self.backup_dir),
            compression="zip",
            incremental=True,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_healthy_vault_diagnostics(self):
        engine = BackupEngine(self.config)
        engine.run_backup(force_full=True)
        time.sleep(1.05)
        (self.source_dir / "a.txt").write_text("alpha v2", encoding="utf-8")
        engine.run_backup()

        diag = BackupDoctor(self.config).run_diagnostics()
        self.assertEqual(diag["health_status"], "HEALTHY")
        self.assertEqual(diag["total_snapshots"], 2)
        self.assertEqual(diag["valid_snapshots"], 2)
        self.assertEqual(diag["corrupt_snapshots"], [])
        self.assertEqual(diag["broken_chains"], [])

    def test_detects_broken_chain_and_orphan_archive(self):
        engine = BackupEngine(self.config)
        snap1 = engine.run_backup(force_full=True)
        time.sleep(1.05)
        (self.source_dir / "a.txt").write_text("alpha v2", encoding="utf-8")
        snap2 = engine.run_backup()

        # Delete snap1 manifest and archive -> breaks snap2 chain
        (self.backup_dir / snap1["archive_name"]).unlink()
        (self.backup_dir / f"{snap1['snapshot_id']}.manifest.json").unlink()

        # Drop an orphaned archive matching task_name
        (self.backup_dir / "doctor_job_orphan.zip").write_bytes(b"orphan")

        diag = BackupDoctor(self.config).run_diagnostics()
        self.assertEqual(diag["health_status"], "CRITICAL")
        self.assertEqual(len(diag["broken_chains"]), 1)
        self.assertEqual(diag["broken_chains"][0]["snapshot_id"], snap2["snapshot_id"])
        self.assertIn(snap1["snapshot_id"], diag["broken_chains"][0]["missing_dependencies"])
        self.assertIn("doctor_job_orphan.zip", diag["orphaned_archives"])

    def test_warning_on_duplicate_waste(self):
        (self.source_dir / "c.txt").write_text("alpha", encoding="utf-8")  # duplicate of a.txt
        engine = BackupEngine(self.config)
        engine.run_backup(force_full=True)

        diag = BackupDoctor(self.config).run_diagnostics()
        self.assertEqual(diag["health_status"], "WARNING")
        self.assertEqual(diag["duplicate_summary"]["duplicate_groups_count"], 1)
        self.assertGreater(diag["duplicate_summary"]["wasted_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
