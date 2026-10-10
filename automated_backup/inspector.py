"""
ByteVault Inspector & Diff Engine
Allows granular inspection of snapshot contents and detailed diffing between snapshots or against live files.
"""

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from automated_backup.config import BackupConfig
from automated_backup.engine import BackupEngine
from automated_backup.hasher import compare_manifests, scan_source

logger = logging.getLogger(__name__)


class SnapshotInspector:
    """Provides tools to inspect snapshot internals and compute diffs."""

    def __init__(self, config: BackupConfig):
        self.config = config
        self.engine = BackupEngine(config)
        self.dest_dir = Path(config.backup_dest).resolve()

    def get_snapshot_manifest(self, snapshot_id: str) -> Dict[str, Any]:
        """Fetch snapshot manifest by ID (or 'latest')."""
        if snapshot_id == "latest":
            latest = self.engine.get_latest_snapshot()
            if not latest:
                raise FileNotFoundError("No snapshots found in backup directory.")
            return latest

        manifest_file = self.dest_dir / f"{snapshot_id}.manifest.json"
        if not manifest_file.is_file():
            candidates = list(self.dest_dir.glob(f"*{snapshot_id}*.manifest.json"))
            if candidates:
                manifest_file = candidates[0]
            else:
                raise FileNotFoundError(f"Snapshot manifest not found: {snapshot_id}")

        with open(manifest_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def inspect_snapshot(self, snapshot_id: str) -> Dict[str, Any]:
        """Inspect the contents of a single snapshot.

        Returns:
            Dictionary containing metadata and the full file tree with sources and origin snapshots.
        """
        manifest = self.get_snapshot_manifest(snapshot_id)
        full_state = manifest.get("full_state", manifest.get("included_files", {}))

        files_list = []
        for rel_path, meta in sorted(full_state.items()):
            files_list.append({
                "path": rel_path,
                "size": meta.get("size", 0),
                "sha256": meta.get("sha256"),
                "origin_snapshot": meta.get("snapshot_id", manifest.get("snapshot_id")),
                "mtime": meta.get("mtime")
            })

        return {
            "snapshot_id": manifest.get("snapshot_id"),
            "task_name": manifest.get("task_name"),
            "timestamp": manifest.get("timestamp"),
            "type": manifest.get("type"),
            "archive_name": manifest.get("archive_name"),
            "archive_size_bytes": manifest.get("archive_size_bytes", 0),
            "files_count": len(files_list),
            "total_uncompressed_bytes": sum(f["size"] for f in files_list),
            "files": files_list
        }

    def diff_snapshots(self, snap_id1: str, snap_id2: str) -> Dict[str, Any]:
        """Compute the difference between two recorded snapshots."""
        snap1 = self.get_snapshot_manifest(snap_id1)
        snap2 = self.get_snapshot_manifest(snap_id2)

        state1 = snap1.get("full_state", snap1.get("included_files", {}))
        state2 = snap2.get("full_state", snap2.get("included_files", {}))

        diff = compare_manifests(state1, state2)

        size_delta = sum(state2[k]["size"] for k in diff["added"] + diff["modified"]) - sum(
            state1[k]["size"] for k in diff["deleted"] + diff["modified"]
        )

        return {
            "base_snapshot": snap1.get("snapshot_id"),
            "target_snapshot": snap2.get("snapshot_id"),
            "added": diff["added"],
            "modified": diff["modified"],
            "deleted": diff["deleted"],
            "unchanged_count": len(diff["unchanged"]),
            "size_delta_bytes": size_delta,
        }

    def diff_live(self, snapshot_id: str = "latest") -> Dict[str, Any]:
        """Compare the current live source directory against a recorded snapshot to preview changes."""
        snap = self.get_snapshot_manifest(snapshot_id)
        recorded_state = snap.get("full_state", snap.get("included_files", {}))

        current_manifest, _ = self.engine.scan_all_sources()
        diff = compare_manifests(recorded_state, current_manifest)

        bytes_to_backup = sum(current_manifest[k]["size"] for k in diff["added"] + diff["modified"])

        return {
            "compared_against_snapshot": snap.get("snapshot_id"),
            "timestamp": datetime.now().isoformat(),
            "added": diff["added"],
            "modified": diff["modified"],
            "deleted": diff["deleted"],
            "unchanged_count": len(diff["unchanged"]),
            "pending_backup_bytes": bytes_to_backup,
            "has_changes": bool(diff["added"] or diff["modified"] or diff["deleted"])
        }
