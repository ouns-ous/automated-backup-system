"""
ByteVault Restore Engine
Handles reconstruction and extraction of full and incremental snapshots to target directories
with full cryptographic integrity verification.
"""

from datetime import datetime
import json
import logging
from pathlib import Path
import shutil
import tarfile
from typing import Any, Dict, List, Optional
import zipfile

from automated_backup.hasher import calculate_file_hash

logger = logging.getLogger(__name__)


class RestoreEngine:
    """Restores snapshots with full chain resolution and integrity checks."""

    def __init__(self, backup_dest: Path):
        self.dest_dir = Path(backup_dest).resolve()

    def get_manifest(self, snapshot_id: str) -> Dict[str, Any]:
        """Locate and read manifest for a snapshot ID."""
        manifest_path = self.dest_dir / f"{snapshot_id}.manifest.json"
        if not manifest_path.is_file():
            # Try searching if full filename wasn't passed
            candidates = list(self.dest_dir.glob(f"*{snapshot_id}*.manifest.json"))
            if candidates:
                manifest_path = candidates[0]
            else:
                raise FileNotFoundError(f"No manifest found for snapshot: {snapshot_id}")

        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def restore(
        self,
        snapshot_id: str,
        target_dir: Path,
        verify_checksums: bool = True
    ) -> Dict[str, Any]:
        """Restore a snapshot to target directory.

        Args:
            snapshot_id: ID of snapshot to restore (e.g. 'backup_job_20261009_160000_full').
            target_dir: Destination directory on disk.
            verify_checksums: Whether to verify SHA-256 hashes of restored files.

        Returns:
            Dictionary with restoration metrics and integrity status.
        """
        start_time = datetime.now()
        target = Path(target_dir).resolve()
        target.mkdir(parents=True, exist_ok=True)

        manifest = self.get_manifest(snapshot_id)
        full_state = manifest.get("full_state", {})

        if not full_state:
            # Fallback to included_files if full_state is missing
            full_state = manifest.get("included_files", {})

        # Group files to extract by snapshot archive
        # mapping: snapshot_id -> list of relative paths
        grouped: Dict[str, List[str]] = {}
        for rel_path, file_meta in full_state.items():
            file_snapshot = file_meta.get("snapshot_id", manifest["snapshot_id"])
            grouped.setdefault(file_snapshot, []).append(rel_path)

        extracted_count = 0
        total_bytes = 0

        for snap_id, rel_paths in grouped.items():
            snap_manifest = self.get_manifest(snap_id)
            archive_name = snap_manifest["archive_name"]
            archive_path = self.dest_dir / archive_name
            compression = snap_manifest.get("compression", "zip").lower()

            if not archive_path.exists():
                raise FileNotFoundError(
                    f"Required archive {archive_name} for snapshot {snap_id} is missing!"
                )

            if compression == "zip":
                with zipfile.ZipFile(archive_path, "r") as zf:
                    for rel in rel_paths:
                        dest_file = target / rel
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(rel) as src, open(dest_file, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        extracted_count += 1
                        total_bytes += full_state[rel].get("size", 0)

            elif compression in ("tar.gz", "tar"):
                mode = "r:gz" if compression == "tar.gz" else "r"
                with tarfile.open(archive_path, mode=mode) as tf:
                    for rel in rel_paths:
                        member = tf.getmember(rel)
                        dest_file = target / rel
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        with tf.extractfile(member) as src, open(dest_file, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        extracted_count += 1
                        total_bytes += full_state[rel].get("size", 0)

            elif compression == "none":
                for rel in rel_paths:
                    source_file = archive_path / rel
                    dest_file = target / rel
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_file, dest_file)
                    extracted_count += 1
                    total_bytes += full_state[rel].get("size", 0)

        # Integrity verification
        corrupted_files: List[str] = []
        if verify_checksums:
            for rel_path, file_meta in full_state.items():
                dest_file = target / rel_path
                expected_sha = file_meta.get("sha256")
                if expected_sha and dest_file.is_file():
                    computed_sha = calculate_file_hash(dest_file)
                    if computed_sha != expected_sha:
                        corrupted_files.append(rel_path)

        duration = (datetime.now() - start_time).total_seconds()
        success = len(corrupted_files) == 0

        return {
            "status": "success" if success else "corrupted",
            "snapshot_id": snapshot_id,
            "target_dir": str(target),
            "restored_files_count": extracted_count,
            "total_bytes": total_bytes,
            "verified": verify_checksums,
            "corrupted_files": corrupted_files,
            "duration_seconds": round(duration, 3),
        }
