"""
ByteVault Diagnostics & Chain Integrity Doctor
Audits all snapshots, verifies archive checksums across all formats, validates
incremental dependency chains, detects orphaned vault files, and summarizes waste.
"""

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Set

from automated_backup.config import BackupConfig
from automated_backup.engine import BackupEngine
from automated_backup.history import FileHistoryEngine

logger = logging.getLogger(__name__)


class BackupDoctor:
    """Comprehensive health checker for a ByteVault backup repository."""

    def __init__(self, config: BackupConfig):
        self.config = config
        self.engine = BackupEngine(config)
        self.history = FileHistoryEngine(config)
        self.dest_dir = Path(config.backup_dest).resolve()

    def _find_orphans(self, known_manifests: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Identify orphaned archives or unreadable/unmatched task files in backup_dest."""
        expected_archives: Set[str] = {
            s["archive_name"] for s in known_manifests if s.get("archive_name")
        }
        expected_manifests: Set[str] = {
            f"{s['snapshot_id']}.manifest.json"
            for s in known_manifests
            if s.get("snapshot_id")
        }

        orphaned_archives: List[str] = []
        orphaned_manifests: List[str] = []
        prefix = f"{self.config.task_name}_"

        if not self.dest_dir.exists():
            return {"orphaned_archives": [], "orphaned_manifests": []}

        for entry in sorted(self.dest_dir.iterdir()):
            if not entry.name.startswith(prefix):
                continue
            if entry.name.endswith(".manifest.json"):
                if entry.name not in expected_manifests:
                    orphaned_manifests.append(entry.name)
                    continue
                # Check if manifest references a missing archive
                try:
                    with open(entry, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    arc_name = data.get("archive_name")
                    if arc_name and not (self.dest_dir / arc_name).exists():
                        orphaned_manifests.append(entry.name)
                except (json.JSONDecodeError, OSError):
                    orphaned_manifests.append(entry.name)
            elif entry.name not in expected_archives:
                orphaned_archives.append(entry.name)

        return {
            "orphaned_archives": orphaned_archives,
            "orphaned_manifests": orphaned_manifests,
        }

    def run_diagnostics(self) -> Dict[str, Any]:
        """Run full vault diagnostics: verification, chain checks, orphan scan, and dedupe audit."""
        snapshots = self.engine.get_existing_snapshots()
        snap_by_id = {s["snapshot_id"]: s for s in snapshots if "snapshot_id" in s}

        verification_results: List[Dict[str, Any]] = []
        corrupt_snapshots: List[str] = []
        broken_chains: List[Dict[str, Any]] = []

        # 1. Verify every snapshot archive and embedded file checksums
        verified_map: Dict[str, bool] = {}
        for snap in snapshots:
            sid = snap["snapshot_id"]
            vres = self.engine.verify_snapshot(sid)
            is_valid = bool(vres.get("valid"))
            verified_map[sid] = is_valid
            verification_results.append({
                "snapshot_id": sid,
                "type": snap.get("type"),
                "valid": is_valid,
                "error": vres.get("error"),
            })
            if not is_valid:
                corrupt_snapshots.append(sid)

        # 2. Verify incremental dependency chains (base_snapshot_id & full_state origin snapshots)
        for snap in snapshots:
            sid = snap["snapshot_id"]
            missing_deps: Set[str] = set()
            unhealthy_deps: Set[str] = set()

            base_id = snap.get("base_snapshot_id")
            if base_id:
                if base_id not in snap_by_id:
                    missing_deps.add(base_id)
                elif not verified_map.get(base_id, False):
                    unhealthy_deps.add(base_id)

            for meta in snap.get("full_state", {}).values():
                origin = meta.get("snapshot_id")
                if origin and origin != sid:
                    if origin not in snap_by_id:
                        missing_deps.add(origin)
                    elif not verified_map.get(origin, False):
                        unhealthy_deps.add(origin)

            if missing_deps or unhealthy_deps:
                broken_chains.append({
                    "snapshot_id": sid,
                    "missing_dependencies": sorted(missing_deps),
                    "corrupt_dependencies": sorted(unhealthy_deps),
                })

        # 3. Scan for orphaned files
        orphans = self._find_orphans(snapshots)

        # 4. Duplicate waste summary on latest snapshot
        duplicate_summary: Dict[str, Any] = {
            "duplicate_groups_count": 0,
            "total_duplicate_files": 0,
            "wasted_bytes": 0,
        }
        if snapshots:
            try:
                dup = self.history.find_duplicate_files("latest")
                duplicate_summary = {
                    "duplicate_groups_count": dup["duplicate_groups_count"],
                    "total_duplicate_files": dup["total_duplicate_files"],
                    "wasted_bytes": dup["wasted_bytes"],
                }
            except Exception as exc:
                logger.warning(f"Duplicate analysis skipped: {exc}")

        has_critical = bool(corrupt_snapshots or broken_chains)
        has_warning = bool(
            orphans["orphaned_archives"]
            or orphans["orphaned_manifests"]
            or duplicate_summary["wasted_bytes"] > 0
        )

        if has_critical:
            health_status = "CRITICAL"
        elif has_warning:
            health_status = "WARNING"
        else:
            health_status = "HEALTHY"

        return {
            "task_name": self.config.task_name,
            "checked_at": datetime.now().isoformat(),
            "health_status": health_status,
            "total_snapshots": len(snapshots),
            "valid_snapshots": sum(1 for v in verified_map.values() if v),
            "corrupt_snapshots": corrupt_snapshots,
            "broken_chains": broken_chains,
            "orphaned_archives": orphans["orphaned_archives"],
            "orphaned_manifests": orphans["orphaned_manifests"],
            "duplicate_summary": duplicate_summary,
            "snapshot_checks": verification_results,
        }
