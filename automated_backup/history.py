"""
ByteVault File History & Duplicate Analyzer
Tracks individual file revisions across snapshot timelines, restores specific
historical file versions, and identifies duplicate storage waste via SHA-256.
"""

from collections import defaultdict
import fnmatch
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from automated_backup.config import BackupConfig
from automated_backup.engine import BackupEngine
from automated_backup.restore import RestoreEngine

logger = logging.getLogger(__name__)


class FileHistoryEngine:
    """Provides point-in-time file revision history and duplicate file analysis."""

    def __init__(self, config: BackupConfig):
        self.config = config
        self.engine = BackupEngine(config)
        self.dest_dir = Path(config.backup_dest).resolve()

    @staticmethod
    def _matches_pattern(rel_path: str, pattern: str) -> bool:
        """Match normalized relative path or basename against a user query/glob."""
        norm_path = rel_path.replace("\\", "/")
        norm_pat = pattern.replace("\\", "/").strip()
        filename = Path(norm_path).name
        return (
            norm_path == norm_pat
            or filename == norm_pat
            or fnmatch.fnmatch(norm_path, norm_pat)
            or fnmatch.fnmatch(filename, norm_pat)
        )

    def get_file_history(
        self,
        pattern: str,
        changes_only: bool = False
    ) -> Dict[str, Any]:
        """Trace revision history for files matching a path or glob across all snapshots.

        Args:
            pattern: Exact relative path, filename, or glob pattern (e.g. '*.py', 'docs/*').
            changes_only: If True, omit 'UNCHANGED' entries from per-file timelines.

        Returns:
            Dictionary containing matched file paths and their chronological revisions.
        """
        snapshots = self.engine.get_existing_snapshots()
        matched_paths: set = set()
        snap_states: List[Dict[str, Any]] = []

        for snap in snapshots:
            state = snap.get("full_state", snap.get("included_files", {}))
            matching_in_snap = {
                path: meta
                for path, meta in state.items()
                if self._matches_pattern(path, pattern)
            }
            matched_paths.update(matching_in_snap.keys())
            snap_states.append({
                "snapshot_id": snap.get("snapshot_id"),
                "timestamp": snap.get("timestamp"),
                "type": snap.get("type"),
                "matches": matching_in_snap,
            })

        files_history: Dict[str, List[Dict[str, Any]]] = {}
        for rel_path in sorted(matched_paths):
            timeline: List[Dict[str, Any]] = []
            prev_meta: Optional[Dict[str, Any]] = None

            for entry in snap_states:
                curr_meta = entry["matches"].get(rel_path)
                if curr_meta is None:
                    if prev_meta is not None:
                        timeline.append({
                            "snapshot_id": entry["snapshot_id"],
                            "timestamp": entry["timestamp"],
                            "status": "DELETED",
                            "size": 0,
                            "sha256": None,
                            "origin_snapshot": None,
                        })
                        prev_meta = None
                    continue

                if prev_meta is None:
                    status = "ADDED"
                elif (
                    curr_meta.get("sha256") != prev_meta.get("sha256")
                    or curr_meta.get("size") != prev_meta.get("size")
                ):
                    status = "MODIFIED"
                else:
                    status = "UNCHANGED"

                if not (changes_only and status == "UNCHANGED"):
                    timeline.append({
                        "snapshot_id": entry["snapshot_id"],
                        "timestamp": entry["timestamp"],
                        "status": status,
                        "size": curr_meta.get("size", 0),
                        "sha256": curr_meta.get("sha256"),
                        "origin_snapshot": curr_meta.get("snapshot_id", entry["snapshot_id"]),
                    })

                prev_meta = curr_meta

            files_history[rel_path] = timeline

        return {
            "pattern": pattern,
            "snapshots_scanned": len(snapshots),
            "matched_files_count": len(files_history),
            "files": files_history,
        }

    def restore_file_version(
        self,
        file_path: str,
        snapshot_id: str,
        target_dir: Path,
        verify_checksum: bool = True,
    ) -> Dict[str, Any]:
        """Restore a single historical file version from a specified snapshot.

        Args:
            file_path: Exact virtual relative path of the file inside the snapshot.
            snapshot_id: Snapshot ID (or 'latest') to restore from.
            target_dir: Destination directory where the file should be restored.
            verify_checksum: Whether to verify SHA-256 after extraction.

        Returns:
            Restore result dictionary from RestoreEngine.
        """
        restore_engine = RestoreEngine(self.dest_dir)
        target_snap = snapshot_id
        if target_snap == "latest":
            latest = self.engine.get_latest_snapshot()
            if not latest:
                raise FileNotFoundError("No snapshots available to restore from.")
            target_snap = latest["snapshot_id"]

        manifest = restore_engine.get_manifest(target_snap)
        state = manifest.get("full_state", manifest.get("included_files", {}))
        norm_query = file_path.replace("\\", "/")
        if norm_query not in state:
            raise FileNotFoundError(
                f"File '{norm_query}' does not exist in snapshot '{target_snap}'."
            )

        return restore_engine.restore(
            snapshot_id=target_snap,
            target_dir=Path(target_dir),
            verify_checksums=verify_checksum,
            include_patterns=[norm_query],
            overwrite=True,
        )

    def find_duplicate_files(self, snapshot_id: str = "latest") -> Dict[str, Any]:
        """Detect identical files within a snapshot using recorded SHA-256 digests.

        Args:
            snapshot_id: Snapshot ID to analyze, or 'latest'.

        Returns:
            Dictionary summarizing duplicate file groups and reclaimable byte waste.
        """
        if snapshot_id == "latest":
            manifest = self.engine.get_latest_snapshot()
            if not manifest:
                raise FileNotFoundError("No snapshots found to analyze.")
        else:
            restore_engine = RestoreEngine(self.dest_dir)
            manifest = restore_engine.get_manifest(snapshot_id)

        state = manifest.get("full_state", manifest.get("included_files", {}))
        by_hash: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for rel_path, meta in sorted(state.items()):
            digest = meta.get("sha256")
            size = meta.get("size", 0)
            if digest and size > 0:
                by_hash[digest].append({"path": rel_path, "size": size})

        duplicate_groups: List[Dict[str, Any]] = []
        wasted_bytes = 0
        total_duplicate_files = 0

        for digest, entries in by_hash.items():
            if len(entries) > 1:
                file_size = entries[0]["size"]
                group_waste = file_size * (len(entries) - 1)
                wasted_bytes += group_waste
                total_duplicate_files += len(entries)
                duplicate_groups.append({
                    "sha256": digest,
                    "size": file_size,
                    "count": len(entries),
                    "wasted_bytes": group_waste,
                    "paths": [e["path"] for e in entries],
                })

        duplicate_groups.sort(key=lambda g: g["wasted_bytes"], reverse=True)

        return {
            "snapshot_id": manifest.get("snapshot_id"),
            "total_files": len(state),
            "duplicate_groups_count": len(duplicate_groups),
            "total_duplicate_files": total_duplicate_files,
            "wasted_bytes": wasted_bytes,
            "groups": duplicate_groups,
        }
