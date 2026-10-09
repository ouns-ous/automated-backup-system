"""
ByteVault Hasher & Manifest Module
Provides cryptographic hashing (SHA-256) and directory state manifest generation.
"""

import fnmatch
import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def calculate_file_hash(file_path: Path, chunk_size: int = 65536) -> str:
    """Compute the SHA-256 hexadecimal hash of a file safely in streaming chunks.

    Args:
        file_path: Absolute or relative Path to target file.
        chunk_size: Byte chunk size for streaming. Defaults to 64KB.

    Returns:
        Hex-encoded SHA-256 digest string.
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def is_excluded(relative_path_str: str, patterns: Optional[List[str]]) -> bool:
    """Check whether a relative path matches any exclusion glob patterns.

    Args:
        relative_path_str: Normalized forward-slash relative path or file name.
        patterns: List of glob patterns (e.g. ['*.tmp', '.git/*']).

    Returns:
        True if the path matches an exclusion pattern, False otherwise.
    """
    if not patterns:
        return False

    normalized = relative_path_str.replace("\\", "/")
    filename = Path(relative_path_str).name

    for pattern in patterns:
        norm_pattern = pattern.replace("\\", "/")
        # Match against full relative path or filename
        if fnmatch.fnmatch(normalized, norm_pattern):
            return True
        if fnmatch.fnmatch(filename, norm_pattern):
            return True
        # Match path components (e.g., .git inside subdirectories)
        for part in normalized.split("/"):
            if fnmatch.fnmatch(part, norm_pattern.rstrip("/*")):
                return True
    return False


def scan_source(
    source_dir: Path,
    exclude_patterns: Optional[List[str]] = None,
    calculate_hashes: bool = True
) -> Dict[str, Dict[str, Any]]:
    """Scan a source directory and generate a manifest of files.

    Args:
        source_dir: Directory path to scan.
        exclude_patterns: Optional glob patterns to filter out unwanted files.
        calculate_hashes: Whether to compute SHA-256 hashes for each file.

    Returns:
        Dictionary mapping normalized relative paths to file metadata:
        {
            "rel_path": str,
            "size": int,
            "mtime": float,
            "sha256": str (or None)
        }
    """
    manifest: Dict[str, Dict[str, Any]] = {}
    source_dir = Path(source_dir).resolve()

    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory does not exist: {source_dir}")

    for root, dirs, files in os.walk(source_dir):
        rel_root = os.path.relpath(root, source_dir)
        norm_rel_root = "" if rel_root == "." else rel_root.replace("\\", "/")

        # Prune excluded directories from traversal
        dirs[:] = [
            d for d in dirs
            if not is_excluded(
                f"{norm_rel_root}/{d}" if norm_rel_root else d,
                exclude_patterns
            )
        ]

        for file_name in files:
            full_path = Path(root) / file_name
            rel_file = (
                f"{norm_rel_root}/{file_name}" if norm_rel_root else file_name
            )

            if is_excluded(rel_file, exclude_patterns):
                continue

            try:
                stat = full_path.stat()
                file_hash = (
                    calculate_file_hash(full_path) if calculate_hashes else None
                )
                manifest[rel_file] = {
                    "rel_path": rel_file,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "sha256": file_hash,
                }
            except (OSError, PermissionError):
                # Ignore files that cannot be read or are locked
                continue

    return manifest


def compare_manifests(
    prev_manifest: Dict[str, Dict[str, Any]],
    curr_manifest: Dict[str, Dict[str, Any]]
) -> Dict[str, List[str]]:
    """Compare an earlier manifest with a current manifest.

    Args:
        prev_manifest: Previous snapshot file manifest.
        curr_manifest: Current scanned file manifest.

    Returns:
        Dictionary categorized into 'added', 'modified', 'deleted', and 'unchanged'.
    """
    prev_keys = set(prev_manifest.keys())
    curr_keys = set(curr_manifest.keys())

    added = sorted(list(curr_keys - prev_keys))
    deleted = sorted(list(prev_keys - curr_keys))
    modified: List[str] = []
    unchanged: List[str] = []

    common = prev_keys & curr_keys
    for k in sorted(list(common)):
        prev_item = prev_manifest[k]
        curr_item = curr_manifest[k]

        # Consider changed if hash differs or size/mtime differ
        hash_differs = (
            prev_item.get("sha256") and curr_item.get("sha256")
            and prev_item.get("sha256") != curr_item.get("sha256")
        )
        meta_differs = (
            prev_item.get("size") != curr_item.get("size")
            or abs(prev_item.get("mtime", 0) - curr_item.get("mtime", 0)) > 1e-4
        )

        if hash_differs or (prev_item.get("sha256") is None and meta_differs):
            modified.append(k)
        else:
            unchanged.append(k)

    return {
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "unchanged": unchanged,
    }
