"""
End-to-end CLI tests for ByteVault.
"""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import time
import unittest

from automated_backup.cli import main
from automated_backup.config import BackupConfig, save_config


class TestCLI(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

        self.source_dir = self.base_path / "source"
        self.backup_dir = self.base_path / "backups"
        self.restore_dir = self.base_path / "restored"
        self.config_path = self.base_path / "backup_config.json"

        self.source_dir.mkdir()
        self.backup_dir.mkdir()
        self.restore_dir.mkdir()

        (self.source_dir / "doc.txt").write_text("hello world", encoding="utf-8")
        (self.source_dir / "copy.txt").write_text("hello world", encoding="utf-8")
        (self.source_dir / "script.py").write_text("print(1)", encoding="utf-8")

        cfg = BackupConfig(
            task_name="cli_job",
            source_dirs=[str(self.source_dir)],
            backup_dest=str(self.backup_dir),
            compression="zip",
            incremental=True,
        )
        save_config(cfg, self.config_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _run_cli(self, args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(args)
        return code, buf.getvalue()

    def test_full_cli_workflow(self):
        # 1. init
        init_cfg = self.base_path / "starter.json"
        code, _ = self._run_cli(["init", "-o", str(init_cfg)])
        self.assertEqual(code, 0)
        self.assertTrue(init_cfg.is_file())

        # 2. run backup
        code, out = self._run_cli(["run", "-c", str(self.config_path)])
        self.assertEqual(code, 0)
        self.assertIn("cli_job_", out)

        time.sleep(1.05)
        (self.source_dir / "script.py").write_text("print(2)", encoding="utf-8")
        code, _ = self._run_cli(["run", "-c", str(self.config_path)])
        self.assertEqual(code, 0)

        # 3. list & verify
        code, list_out = self._run_cli(["list", "-c", str(self.config_path)])
        self.assertEqual(code, 0)
        self.assertIn("cli_job_", list_out)

        code, verify_out = self._run_cli(["verify", "-c", str(self.config_path)])
        self.assertEqual(code, 0)
        self.assertIn("PASSED", verify_out)

        # 4. selective restore dry-run and real restore
        code, dry_out = self._run_cli([
            "restore", "-c", str(self.config_path),
            "-t", str(self.restore_dir),
            "--include", "*.py",
            "--dry-run",
        ])
        self.assertEqual(code, 0)
        self.assertIn("DRY RUN", dry_out)
        self.assertIn("script.py", dry_out)

        code, _ = self._run_cli([
            "restore", "-c", str(self.config_path),
            "-t", str(self.restore_dir),
            "--include", "*.py",
        ])
        self.assertEqual(code, 0)
        self.assertEqual((self.restore_dir / "script.py").read_text(encoding="utf-8"), "print(2)")
        self.assertFalse((self.restore_dir / "doc.txt").exists())

        # 5. history & dedupe
        code, hist_out = self._run_cli(["history", "script.py", "-c", str(self.config_path)])
        self.assertEqual(code, 0)
        self.assertIn("ADDED", hist_out)
        self.assertIn("MODIFIED", hist_out)

        code, dedupe_out = self._run_cli(["dedupe", "-c", str(self.config_path)])
        self.assertEqual(code, 0)
        self.assertIn("Duplicate Groups:", dedupe_out)

        # 6. doctor --json
        code, doc_out = self._run_cli(["doctor", "-c", str(self.config_path), "--json"])
        self.assertEqual(code, 0)
        diag = json.loads(doc_out)
        self.assertEqual(diag["health_status"], "WARNING")  # duplicates present, chains valid
        self.assertEqual(diag["valid_snapshots"], 2)


if __name__ == "__main__":
    unittest.main()
