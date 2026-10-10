"""
Tests for Watcher and automated scheduler.
"""

from pathlib import Path
import tempfile
import time
import unittest

from automated_backup.config import BackupConfig
from automated_backup.engine import BackupEngine
from automated_backup.watcher import BackupWatcher


class TestBackupWatcher(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

        self.source_dir = self.base_path / "source"
        self.backup_dir = self.base_path / "backups"
        self.source_dir.mkdir()
        self.backup_dir.mkdir()

        (self.source_dir / "init.txt").write_text("initial file", encoding="utf-8")

        self.config = BackupConfig(
            task_name="watch_job",
            source_dirs=[str(self.source_dir)],
            backup_dest=str(self.backup_dir),
            compression="zip",
            incremental=True,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_check_for_changes(self):
        watcher = BackupWatcher(self.config, debounce_seconds=0.1)

        # Before any backup, has_changes is True
        status = watcher.check_for_changes()
        self.assertTrue(status["has_changes"])
        self.assertEqual(status["reason"], "initial_backup")

        # Run initial backup
        engine = BackupEngine(self.config)
        engine.run_backup(force_full=True)

        # Right after backup, has_changes is False
        status_after = watcher.check_for_changes()
        self.assertFalse(status_after["has_changes"])

        # Create a new file
        time.sleep(0.05)
        (self.source_dir / "new.txt").write_text("added file", encoding="utf-8")

        status_changed = watcher.check_for_changes()
        self.assertTrue(status_changed["has_changes"])
        self.assertEqual(status_changed["added"], 1)

    def test_polling_loop_single_cycle(self):
        # Create initial backup
        engine = BackupEngine(self.config)
        engine.run_backup(force_full=True)

        # Trigger a change
        time.sleep(0.05)
        (self.source_dir / "updated.txt").write_text("trigger content", encoding="utf-8")

        watcher = BackupWatcher(self.config, debounce_seconds=0.1)
        results = []

        cycles = watcher.run_polling_loop(
            poll_interval=0.05,
            max_cycles=1,
            on_backup_callback=lambda res: results.append(res)
        )

        self.assertEqual(cycles, 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "success")
        self.assertEqual(results[0]["type"], "inc")


if __name__ == "__main__":
    unittest.main()
