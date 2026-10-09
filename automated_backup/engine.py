"""
ByteVault Backup Engine
Core backup execution handling full and incremental snapshots, archive packing,
and snapshot manifest generation.
"""

from datetime import datetime
import json
import logging
import os
from pathlib import Path
import shutil
import tarfile
from typing import Any, Dict, List, Optional, Tuple
import zipfile

from automated_backup.config import BackupConfig
from automated_backup.hasher import (
    calculate_file_hash,
    compare_manifests,
    is_excluded,
    scan_source,
)

logger = logging.getLogger(__name__)


class BackupEngine:
    """Orchestrates scanning, diffing, archiving, and snapshot tracking."""

    def __init__(self, config: BackupConfig):
        self.config = config
        self.dest_dir = Path(config.backup_dest).resolve()
        self.dest_dir.mkdir(parents=True, exist_ok=True)

    def _generate_snapshot_id(self, snapshot_type: str) -> str:
        """Create a unique timestamped snapshot ID."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{self.config.task_name}_{ts}_{snapshot_type}"

    def get_existing_snapshots(self) -> List[Dict[str, Any]]:
        """Find and parse all manifest files in the destination directory, sorted oldest to newest."""
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
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read snapshot manifest {mf}: {e}")
        return snapshots

    def get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        """Get the most recent snapshot for the configured task, or None if no prior snapshots exist."""
        snapshots = self.get_existing_snapshots()
        return snapshots[-1] if snapshots else None

    def scan_all_sources(self) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Path]]:
        """Scan all source folders configured and generate a merged virtual file manifest.

        Returns:
            Tuple containing:
            1. Merged manifest dictionary: rel_path -> metadata
            2. Lookup table: rel_path -> actual absolute Path on disk
        """
        merged_manifest: Dict[str, Dict[str, Any]] = {}
        path_lookup: Dict[str, Path] = {}

        is_multi_source = len(self.config.source_dirs) > 1

        for src_str in self.config.source_dirs:
            src_path = Path(src_str).resolve()
            if not src_path.exists():
                logger.warning(f"Source directory not found, skipping: {src_path}")
                continue

            folder_prefix = src_path.name if is_multi_source else ""
            raw_manifest = scan_source(src_path, self.config.exclude_patterns, calculate_hashes=True)

            for rel_file, meta in raw_manifest.items():
                virtual_rel = f"{folder_prefix}/{rel_file}" if folder_prefix else rel_file
                virtual_meta = dict(meta)
                virtual_meta["virtual_rel_path"] = virtual_rel
                virtual_meta["source_root"] = str(src_path)

                merged_manifest[virtual_rel] = virtual_meta
                path_lookup[virtual_rel] = src_path / rel_file

        return merged_manifest, path_lookup

    def run_backup(
        self,
        force_full: bool = False,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Execute a backup operation.

        Args:
            force_full: If True, forces a full backup even if incremental is enabled.
            dry_run: If True, simulates changes without writing archives or manifests.

        Returns:
            Summary dictionary containing snapshot details and statistics.
        """
        start_time = datetime.now()
        current_manifest, path_lookup = self.scan_all_sources()

        latest_snapshot = self.get_latest_snapshot()
        is_incremental = (
            self.config.incremental
            and not force_full
            and latest_snapshot is not None
        )

        snapshot_type = "inc" if is_incremental else "full"
        snapshot_id = self._generate_snapshot_id(snapshot_type)

        files_to_pack: List[str] = []
        changes_summary: Dict[str, Any] = {
            "added": 0,
            "modified": 0,
            "deleted": 0,
            "unchanged": 0
        }
        reconstructed_state: Dict[str, Any] = {}

        if is_incremental and latest_snapshot:
            prev_state = latest_snapshot.get("full_state", {})
            diff = compare_manifests(prev_state, current_manifest)

            files_to_pack = diff["added"] + diff["modified"]
            changes_summary = {
                "added": len(diff["added"]),
                "modified": len(diff["modified"]),
                "deleted": len(diff["deleted"]),
                "unchanged": len(diff["unchanged"]),
            }

            # Build full reconstructed state:
            # - Carry forward unchanged items from previous state
            # - Update added and modified items to point to current snapshot_id
            for k in diff["unchanged"]:
                if k in prev_state:
                    reconstructed_state[k] = prev_state[k]

            for k in diff["added"] + diff["modified"]:
                item = dict(current_manifest[k])
                item["snapshot_id"] = snapshot_id
                reconstructed_state[k] = item

            base_snapshot_id = latest_snapshot["snapshot_id"]
        else:
            files_to_pack = sorted(list(current_manifest.keys()))
            changes_summary = {
                "added": len(files_to_pack),
                "modified": 0,
                "deleted": 0,
                "unchanged": 0,
            }
            for k in files_to_pack:
                item = dict(current_manifest[k])
                item["snapshot_id"] = snapshot_id
                reconstructed_state[k] = item

            base_snapshot_id = None

        total_bytes = sum(current_manifest[k]["size"] for k in files_to_pack)

        if dry_run:
            duration = (datetime.now() - start_time).total_seconds()
            return {
                "status": "dry_run",
                "snapshot_id": snapshot_id,
                "type": snapshot_type,
                "files_to_pack_count": len(files_to_pack),
                "total_bytes": total_bytes,
                "changes_summary": changes_summary,
                "duration_seconds": round(duration, 3),
            }

        # Pack archive
        archive_name, archive_path = self._create_archive(
            snapshot_id=snapshot_id,
            files_to_pack=files_to_pack,
            path_lookup=path_lookup
        )

        # Compute archive checksum and size
        if archive_path.is_file():
            archive_sha256 = calculate_file_hash(archive_path)
            archive_size = archive_path.stat().st_size
        else:
            archive_sha256 = "N/A"
            archive_size = sum(f.stat().st_size for f in archive_path.rglob("*") if f.is_file())

        included_files_meta = {k: current_manifest[k] for k in files_to_pack}

        manifest_data: Dict[str, Any] = {
            "snapshot_id": snapshot_id,
            "task_name": self.config.task_name,
            "timestamp": start_time.isoformat(),
            "type": snapshot_type,
            "base_snapshot_id": base_snapshot_id,
            "compression": self.config.compression,
            "archive_name": archive_name,
            "archive_sha256": archive_sha256,
            "archive_size_bytes": archive_size,
            "files_packed_count": len(files_to_pack),
            "packed_bytes": total_bytes,
            "changes_summary": changes_summary,
            "included_files": included_files_meta,
            "full_state": reconstructed_state,
        }

        manifest_file = self.dest_dir / f"{snapshot_id}.manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        duration = (datetime.now() - start_time).total_seconds()
        manifest_data["manifest_path"] = str(manifest_file)
        manifest_data["duration_seconds"] = round(duration, 3)
        manifest_data["status"] = "success"

        return manifest_data

    def _create_archive(
        self,
        snapshot_id: str,
        files_to_pack: List[str],
        path_lookup: Dict[str, Path]
    ) -> Tuple[str, Path]:
        """Pack files into configured archive format."""
        compression = self.config.compression.lower()

        if compression == "zip":
            archive_name = f"{snapshot_id}.zip"
            archive_path = self.dest_dir / archive_name
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for rel_path in files_to_pack:
                    real_path = path_lookup[rel_path]
                    zf.write(real_path, arcname=rel_path)
            return archive_name, archive_path

        elif compression in ("tar.gz", "tar"):
            mode = "w:gz" if compression == "tar.gz" else "w"
            ext = ".tar.gz" if compression == "tar.gz" else ".tar"
            archive_name = f"{snapshot_id}{ext}"
            archive_path = self.dest_dir / archive_name
            with tarfile.open(archive_path, mode=mode) as tf:
                for rel_path in files_to_pack:
                    real_path = path_lookup[rel_path]
                    tf.add(real_path, arcname=rel_path)
            return archive_name, archive_path

        elif compression == "none":
            archive_name = snapshot_id
            archive_path = self.dest_dir / archive_name
            archive_path.mkdir(parents=True, exist_ok=True)
            for rel_path in files_to_pack:
                real_path = path_lookup[rel_path]
                target = archive_path / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(real_path, target)
            return archive_name, archive_path

        else:
            raise ValueError(f"Unsupported compression: {compression}")

    def verify_snapshot(self, snapshot_id: str) -> Dict[str, Any]:
        """Verify the integrity of a snapshot archive and its files against its manifest.

        Args:
            snapshot_id: ID of the snapshot to verify.

        Returns:
            Dictionary with validation status, discrepancies, and details.
        """
        manifest_path = self.dest_dir / f"{snapshot_id}.manifest.json"
        if not manifest_path.is_file():
            return {
                "valid": False,
                "error": f"Manifest not found for snapshot {snapshot_id}"
            }

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        archive_name = manifest_data.get("archive_name")
        archive_path = self.dest_dir / archive_name

        if not archive_path.exists():
            return {
                "valid": False,
                "error": f"Archive {archive_name} does not exist on disk."
            }

        # Check archive checksum if compressed
        if archive_path.is_file():
            recorded_hash = manifest_data.get("archive_sha256")
            actual_hash = calculate_file_hash(archive_path)
            if recorded_hash != "N/A" and actual_hash != recorded_hash:
                return {
                    "valid": False,
                    "error": f"Archive hash mismatch! Recorded: {recorded_hash}, Actual: {actual_hash}"
                }

        # Test archive integrity
        compression = manifest_data.get("compression", "zip")
        corrupt_files = []

        if compression == "zip" and archive_path.is_file():
            try:
                with zipfile.ZipFile(archive_path, "r") as zf:
                    bad_file = zf.testzip()
                    if bad_file:
                        return {
                            "valid": False,
                            "error": f"Corrupt file in zip archive: {bad_file}"
                        }
                    # Also verify file SHA-256 for each included file
                    for item in manifest_data.get("included_files", {}).values():
                        rel = item["rel_path"]
                        expected_hash = item.get("sha256")
                        if expected_hash and rel in zf.namelist():
                            data = zf.read(rel)
                            import hashlib
                            computed = hashlib.sha256(data).hexdigest()
                            if computed != expected_hash:
                                corrupt_files.append(rel)
            except Exception as e:
                return {"valid": False, "error": f"Failed reading zip archive: {e}"}

        if corrupt_files:
            return {
                "valid": False,
                "error": f"Hash mismatch for files within archive: {corrupt_files}"
            }

        return {
            "valid": True,
            "snapshot_id": snapshot_id,
            "type": manifest_data.get("type"),
            "files_packed": manifest_data.get("files_packed_count"),
            "archive_sha256": manifest_data.get("archive_sha256"),
            "verified_at": datetime.now().isoformat(),
        }
