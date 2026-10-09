"""
ByteVault Retention Manager Module
Handles automatic snapshot retention policies based on count and age limits,
ensuring disk space is optimized while maintaining backup chain integrity.
"""

from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Set

from automated_backup.config import BackupConfig

logger = logging.getLogger(__name__)


class RetentionManager:
    """Manages snapshot lifecycle and deletes expired or excess backups."""

    def __init__(self, config: BackupConfig):
        self.config = config
        self.dest_dir = Path(config.backup_dest).resolve()

    def get_snapshots(self) -> List[Dict[str, Any]]:
        """Retrieve all snapshot manifests for this task, sorted chronologically (oldest first)."""
        manifest_files = sorted(
            self.dest_dir.glob(f"{self.config.task_name}_*.manifest.json"),
            key=lambda p: p.stat().st_mtime
        )
        snapshots = []
        for mf in manifest_files:
            try:
                with open(mf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data["manifest_path"] = str(mf)
                    snapshots.append(data)
            except Exception as e:
                logger.warning(f"Could not load manifest {mf}: {e}")
        return snapshots

    def prune_snapshots(
        self,
        retention_count: Optional[int] = None,
        retention_days: Optional[int] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Prune snapshots according to retention count and age rules.

        Args:
            retention_count: Override for config.retention_count.
            retention_days: Override for config.retention_days.
            dry_run: If True, calculates candidates without deleting.

        Returns:
            Dictionary containing pruned snapshot IDs, candidates, and freed bytes.
        """
        count_limit = retention_count if retention_count is not None else self.config.retention_count
        days_limit = retention_days if retention_days is not None else self.config.retention_days

        all_snapshots = self.get_snapshots()
        if not all_snapshots:
            return {
                "total_snapshots": 0,
                "retained_count": 0,
                "pruned_count": 0,
                "pruned_snapshots": [],
                "freed_bytes": 0,
                "dry_run": dry_run,
            }

        # Snapshot chronological order: oldest to newest
        # We always keep at least `count_limit` most recent snapshots
        protected_by_count = set(
            s["snapshot_id"] for s in all_snapshots[-count_limit:]
        ) if count_limit > 0 else set()

        now = datetime.now()
        candidates_to_prune: List[Dict[str, Any]] = []

        for s in all_snapshots:
            sid = s["snapshot_id"]
            if sid in protected_by_count:
                continue

            # Check age limit if configured
            should_prune = False
            if days_limit is not None and days_limit > 0:
                try:
                    snap_time = datetime.fromisoformat(s["timestamp"])
                    if now - snap_time > timedelta(days=days_limit):
                        should_prune = True
                except Exception:
                    # If date parsing fails, fall back to count policy
                    should_prune = True
            else:
                # If only count policy is configured, anything outside count limit is pruned
                should_prune = True

            if should_prune:
                candidates_to_prune.append(s)

        # Ensure we never prune the base of an active incremental snapshot that is retained
        retained_snapshots = [s for s in all_snapshots if s not in candidates_to_prune]
        needed_bases: Set[str] = set()
        for rs in retained_snapshots:
            base = rs.get("base_snapshot_id")
            if base:
                needed_bases.add(base)

        final_prune_list: List[Dict[str, Any]] = []
        for candidate in candidates_to_prune:
            cid = candidate["snapshot_id"]
            if cid in needed_bases:
                logger.info(
                    f"Preserving snapshot {cid} because a retained incremental snapshot depends on it."
                )
                continue
            final_prune_list.append(candidate)

        freed_bytes = 0
        pruned_ids = []

        for snap in final_prune_list:
            sid = snap["snapshot_id"]
            archive_name = snap.get("archive_name")
            manifest_file = Path(snap["manifest_path"])
            archive_path = self.dest_dir / archive_name if archive_name else None

            # Calculate space
            archive_size = 0
            if archive_path and archive_path.exists():
                if archive_path.is_file():
                    archive_size = archive_path.stat().st_size
                elif archive_path.is_dir():
                    archive_size = sum(f.stat().st_size for f in archive_path.rglob("*") if f.is_file())

            freed_bytes += archive_size
            pruned_ids.append(sid)

            if not dry_run:
                # Remove archive
                if archive_path and archive_path.exists():
                    try:
                        if archive_path.is_dir():
                            shutil.rmtree(archive_path)
                        else:
                            archive_path.unlink()
                    except OSError as e:
                        logger.error(f"Error removing archive {archive_path}: {e}")

                # Remove manifest
                if manifest_file.exists():
                    try:
                        manifest_file.unlink()
                    except OSError as e:
                        logger.error(f"Error removing manifest {manifest_file}: {e}")

        return {
            "total_snapshots": len(all_snapshots),
            "retained_count": len(all_snapshots) - len(final_prune_list),
            "pruned_count": len(final_prune_list),
            "pruned_snapshots": pruned_ids,
            "freed_bytes": freed_bytes,
            "dry_run": dry_run,
        }
