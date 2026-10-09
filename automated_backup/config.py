"""
ByteVault Configuration Module
Handles loading, validation, and serialization of backup configurations.
"""

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


SUPPORTED_COMPRESSIONS = {"zip", "tar.gz", "tar", "none"}


@dataclass
class BackupConfig:
    """Dataclass holding all options for a backup operation."""
    task_name: str = "backup_job"
    source_dirs: List[str] = field(default_factory=lambda: ["./data"])
    backup_dest: str = "./backups"
    compression: str = "zip"
    incremental: bool = True
    retention_count: int = 5
    retention_days: Optional[int] = 30
    exclude_patterns: List[str] = field(default_factory=lambda: [
        "*.tmp",
        "*.log",
        "__pycache__/*",
        "*/__pycache__/*",
        ".git/*",
        "*/.git/*",
        "*.swp"
    ])

    def validate(self) -> None:
        """Validate configuration settings, raising ValueError if invalid."""
        if not self.task_name or not self.task_name.strip():
            raise ValueError("Task name cannot be empty.")

        if not self.source_dirs:
            raise ValueError("At least one source directory must be specified.")

        if self.compression.lower() not in SUPPORTED_COMPRESSIONS:
            raise ValueError(
                f"Unsupported compression format: {self.compression}. "
                f"Choose from {sorted(list(SUPPORTED_COMPRESSIONS))}."
            )

        if self.retention_count < 1:
            raise ValueError("retention_count must be at least 1.")

        if self.retention_days is not None and self.retention_days < 0:
            raise ValueError("retention_days cannot be negative.")

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BackupConfig":
        """Build a BackupConfig object from a dictionary."""
        config = cls(
            task_name=str(data.get("task_name", "backup_job")),
            source_dirs=[str(s) for s in data.get("source_dirs", ["./data"])],
            backup_dest=str(data.get("backup_dest", "./backups")),
            compression=str(data.get("compression", "zip")).lower(),
            incremental=bool(data.get("incremental", True)),
            retention_count=int(data.get("retention_count", 5)),
            retention_days=(
                int(data["retention_days"]) if data.get("retention_days") is not None else None
            ),
            exclude_patterns=list(data.get("exclude_patterns", []))
        )
        config.validate()
        return config


def load_config(file_path: Path) -> BackupConfig:
    """Load and parse BackupConfig from a JSON file.

    Args:
        file_path: Path to configuration JSON file.

    Returns:
        Validated BackupConfig object.
    """
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return BackupConfig.from_dict(data)


def save_config(config: BackupConfig, file_path: Path) -> None:
    """Save BackupConfig to a JSON file.

    Args:
        config: BackupConfig object to serialize.
        file_path: Target path for the JSON file.
    """
    path = Path(file_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2)


def create_default_config(dest_path: Path) -> BackupConfig:
    """Generate and write a starter configuration file."""
    config = BackupConfig()
    save_config(config, dest_path)
    return config
