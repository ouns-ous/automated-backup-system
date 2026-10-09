# ByteVault: Automated Data & File Backup System

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Integrity Check](https://img.shields.io/badge/integrity-SHA--256-green.svg)](https://en.wikipedia.org/wiki/SHA-2)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

ByteVault is a resilient, modular, and autonomous Python backup utility engineered for reliable data protection, differential/incremental snapshots, cryptographic integrity checks, and intelligent retention management.

---

## Key Features

- **Full & Incremental Snapshots**:
  - Automatically identifies new, modified, deleted, and unchanged files using cryptographic SHA-256 digests and file metadata.
  - Packs only delta modifications in incremental passes, conserving storage while retaining full point-in-time state reconstruction.
- **Cryptographic Verification**:
  - Generates verifiable `.manifest.json` state metadata for every snapshot.
  - Verifies archive consistency and individual file hashes before and after restoration to guarantee zero bit-rot or file corruption.
- **Smart Retention Policies**:
  - Automatically prunes older snapshots based on maximum count (`retention_count`) or maximum age (`retention_days`).
  - Protects base snapshots actively referenced by downstream incremental chains.
- **Exclusion Filters**:
  - Glob-based pattern filtering for ignoring temporary files, caches, build artifacts, or VCS folders (e.g. `*.tmp`, `__pycache__/*`, `.git/*`).
- **Flexible Archive Compression**:
  - Supports standard `zip` (deflated), `tar.gz`, `tar`, or uncompressed directory mirror mode (`none`).
- **Zero Heavy Dependencies**:
  - Core engine operates exclusively with the standard library with optional rich terminal enhancements.

---

## Directory Structure

```text
automated-backup-system/
├── automated_backup/
│   ├── __init__.py          # Package metadata & version
│   ├── cli.py               # Command-line interface with subcommands
│   ├── config.py            # Dataclass configuration loader & validator
│   ├── engine.py            # Full/incremental backup engine & archiver
│   ├── hasher.py            # SHA-256 streaming hasher & manifest diffing
│   ├── reporter.py          # Formatted reporting (Rich console / ASCII)
│   ├── restore.py           # Snapshot extractor & chain reconstructor
│   └── retention.py         # Retention policy & pruning manager
├── tests/
│   ├── __init__.py
│   ├── test_hasher.py       # Hasher & manifest diff tests
│   ├── test_engine.py       # Full & incremental backup engine tests
│   ├── test_retention.py    # Retention count & dry-run tests
│   └── test_restore.py      # Restore & integrity verification tests
├── config.example.json      # Sample configuration profile
├── main.py                  # CLI application entry point
├── requirements.txt         # Optional UI dependencies
└── README.md                # Documentation
```

---

## Quick Start

### 1. Initialize Configuration

Generate a standard configuration template:

```bash
python main.py init -o backup_config.json
```

Example `backup_config.json`:

```json
{
  "task_name": "work_vault",
  "source_dirs": [
    "./documents",
    "./projects"
  ],
  "backup_dest": "./backups",
  "compression": "zip",
  "incremental": true,
  "retention_count": 5,
  "retention_days": 30,
  "exclude_patterns": [
    "*.tmp",
    "*.log",
    "__pycache__/*",
    "*/__pycache__/*",
    ".git/*",
    "*/.git/*"
  ]
}
```

### 2. Run a Backup Job

Execute an automated backup (creates a full snapshot if first run, or an incremental delta if snapshots already exist):

```bash
python main.py run --config backup_config.json
```

Force a full backup anytime:

```bash
python main.py run --config backup_config.json --full
```

Preview changes without writing archives (`--dry-run`):

```bash
python main.py run --config backup_config.json --dry-run
```

### 3. List Recorded Snapshots

```bash
python main.py list --config backup_config.json
```

### 4. Verify Snapshot Integrity

Validate the archive structure and file-level SHA-256 checksums:

```bash
python main.py verify --config backup_config.json --snapshot latest
```

### 5. Restore Snapshots

Reconstruct source data to a specified destination directory:

```bash
python main.py restore --snapshot latest --target ./restored_data
```

### 6. Manage Retention & Pruning

Enforce retention limits manually:

```bash
python main.py prune --config backup_config.json --keep 3
```

---

## Testing & Quality Assurance

Run the automated test suite with Python's built-in `unittest`:

```bash
python -m unittest discover -s tests -v
```

---

## License

This project is released under the MIT License.
