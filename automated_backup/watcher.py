"""
ByteVault Watcher & Automated Scheduler
Monitors source directories for real-time file changes with debouncing and executes scheduled backups.
"""

from datetime import datetime
import logging
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional

from automated_backup.config import BackupConfig
from automated_backup.engine import BackupEngine
from automated_backup.hasher import compare_manifests
from automated_backup.retention import RetentionManager

logger = logging.getLogger(__name__)


class BackupWatcher:
    """Monitors configured source directories and triggers automated backups upon change or timer."""

    def __init__(self, config: BackupConfig, debounce_seconds: float = 3.0):
        self.config = config
        self.engine = BackupEngine(config)
        self.retention = RetentionManager(config)
        self.debounce_seconds = debounce_seconds

    def check_for_changes(self) -> Dict[str, Any]:
        """Check if any file has been added, modified, or deleted since the latest snapshot."""
        current_manifest, _ = self.engine.scan_all_sources()
        latest = self.engine.get_latest_snapshot()

        if not latest:
            # No prior snapshot means initial full backup is needed
            return {
                "has_changes": True,
                "reason": "initial_backup",
                "added": len(current_manifest),
                "modified": 0,
                "deleted": 0,
            }

        prev_state = latest.get("full_state", latest.get("included_files", {}))
        diff = compare_manifests(prev_state, current_manifest)

        has_changes = bool(diff["added"] or diff["modified"] or diff["deleted"])
        return {
            "has_changes": has_changes,
            "reason": "files_modified" if has_changes else "no_change",
            "added": len(diff["added"]),
            "modified": len(diff["modified"]),
            "deleted": len(diff["deleted"]),
            "unchanged": len(diff["unchanged"]),
        }

    def trigger_backup_cycle(self) -> Optional[Dict[str, Any]]:
        """Trigger an incremental backup and apply retention pruning."""
        logger.info(f"Triggering backup cycle for task '{self.config.task_name}'...")
        res = self.engine.run_backup(force_full=False)
        self.retention.prune_snapshots()
        return res

    def run_polling_loop(
        self,
        poll_interval: float = 2.0,
        max_cycles: Optional[int] = None,
        on_backup_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> int:
        """Run continuous change-detection loop with debouncing.

        Args:
            poll_interval: Seconds between scanning for changes.
            max_cycles: Optional limit on number of successful backup triggers (for testing/automation).
            on_backup_callback: Optional callback invoked with backup result dictionary.

        Returns:
            Number of backups successfully executed.
        """
        logger.info(
            f"Starting ByteVault watcher on sources: {self.config.source_dirs} "
            f"(poll interval: {poll_interval}s, debounce: {self.debounce_seconds}s)"
        )

        completed_backups = 0
        last_change_detected_at: Optional[float] = None

        while True:
            try:
                change_status = self.check_for_changes()

                if change_status["has_changes"]:
                    now = time.time()
                    if last_change_detected_at is None:
                        last_change_detected_at = now
                        logger.info(
                            f"Detected file changes: +{change_status['added']} / "
                            f"~{change_status['modified']} / -{change_status['deleted']}. "
                            f"Debouncing for {self.debounce_seconds}s..."
                        )

                    # Check if debounce window has elapsed
                    elif now - last_change_detected_at >= self.debounce_seconds:
                        res = self.trigger_backup_cycle()
                        completed_backups += 1
                        last_change_detected_at = None

                        if on_backup_callback and res:
                            on_backup_callback(res)

                        if max_cycles and completed_backups >= max_cycles:
                            break
                else:
                    last_change_detected_at = None

                time.sleep(poll_interval)

            except KeyboardInterrupt:
                logger.info("Watcher stopped by user.")
                break

        return completed_backups
