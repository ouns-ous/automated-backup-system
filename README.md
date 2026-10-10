# ByteVault: Automated Data & File Backup System

[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://github.com/ouns-ous/automated-backup-system)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Integrity Check](https://img.shields.io/badge/integrity-SHA--256-green.svg)](https://en.wikipedia.org/wiki/SHA-2)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

ByteVault is a resilient, modular, and autonomous Python backup utility engineered for reliable data protection, differential/incremental snapshots, cryptographic integrity checks, real-time file system watching, and intelligent retention management.

---

## Key Features

- **Full & Incremental Snapshots**:
  - Automatically identifies new, modified, deleted, and unchanged files using cryptographic SHA-256 digests and file metadata.
  - Packs only delta modifications in incremental passes, conserving storage while retaining full point-in-time state reconstruction.
- **Cryptographic Verification**:
  - Generates verifiable `.manifest.json` state metadata for every snapshot.
  - Verifies archive consistency and individual file hashes before and after restoration to guarantee zero bit-rot or file corruption.
- **Real-Time Directory Watcher & Auto-Scheduler (New in v1.1)**:
  - Background polling/watcher monitoring source folders with smart debouncing to trigger automatic incremental backups on file changes.
- **Granular Snapshot Inspection & Diffing (New in v1.1)**:
  - Inspect file trees, hashes, sizes, and origin snapshots (`inspect`).
  - Compare two snapshots or diff current live files against snapshots before backing up (`diff`).
- **Interactive Visual HTML Dashboard & Markdown Reports (New in v1.1)**:
  - Standalone modern dark-mode HTML status dashboard with storage statistics, compression savings, and full snapshot timeline tables (`report`).
- **Smart Retention Policies**:
  - Automatically prunes older snapshots based on maximum count (`retention_count`) or maximum age (`retention_days`).
  - Protects base snapshots actively referenced by downstream incremental chains.
- **Exclusion Filters**:
  - Glob-based pattern filtering for ignoring temporary files, caches, build artifacts, or VCS folders (e.g. `*.tmp`, `__pycache__/*`, `.git/*`).
- **Flexible Archive Compression**:
  - Supports standard `zip` (deflated), `tar.gz`, `tar`, or uncompressed directory mirror mode (`none`).

---

## Directory Structure

```text
automated-backup-system/
├── automated_backup/
│   ├── __init__.py          # Package metadata & version (v1.1.0)
│   ├── cli.py               # Comprehensive CLI with all subcommands
│   ├── config.py            # Dataclass configuration loader & validator
│   ├── dashboard.py         # Visual HTML dashboard & Markdown exporter
│   ├── engine.py            # Full/incremental backup engine & archiver
│   ├── hasher.py            # SHA-256 streaming hasher & manifest diffing
│   ├── inspector.py         # Snapshot inspector & live diff engine
│   ├── reporter.py          # Formatted reporting (Rich console / ASCII)
│   ├── restore.py           # Snapshot extractor & chain reconstructor
│   ├── retention.py         # Retention policy & pruning manager
│   └── watcher.py           # Real-time watcher & debounced auto-sync
├── tests/
│   ├── __init__.py
│   ├── test_dashboard.py    # Dashboard & HTML report generator tests
│   ├── test_engine.py       # Full & incremental backup engine tests
│   ├── test_hasher.py       # Hasher & manifest diff tests
│   ├── test_inspector.py    # Snapshot inspector & diff tests
│   ├── test_restore.py      # Restore & integrity verification tests
│   ├── test_retention.py    # Retention count & dry-run tests
│   └── test_watcher.py      # Watcher & debounced trigger tests
├── config.example.json      # Sample configuration profile
├── main.py                  # CLI application entry point
├── requirements.txt         # Optional UI dependencies
└── README.md                # Documentation
```

---

## Quick Start & CLI Reference

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

### 3. Real-Time Directory Watcher

Continuously monitor configured source directories and auto-trigger debounced incremental backups when files change:

```bash
python main.py watch --config backup_config.json --debounce 3.0
```

### 4. Inspect Snapshot File Tree

View all files within a snapshot, including file sizes and origin snapshots:

```bash
python main.py inspect --config backup_config.json --snapshot latest
```

### 5. Diff Snapshots or Live Changes

Compare live modified files against the latest snapshot:

```bash
python main.py diff --config backup_config.json --live
```

Or compare two historical snapshots:

```bash
python main.py diff --snap1 <snapshot_id_1> --snap2 <snapshot_id_2>
```

### 6. Generate Visual HTML Dashboard Report

Export a standalone, modern dark-mode HTML status dashboard with storage analytics:

```bash
python main.py report --config backup_config.json -o backup_dashboard.html
```

Or export as Markdown:

```bash
python main.py report --config backup_config.json -f markdown -o report.md
```

### 7. List Recorded Snapshots

```bash
python main.py list --config backup_config.json
```

### 8. Verify Snapshot Integrity

Validate the archive structure and file-level SHA-256 checksums:

```bash
python main.py verify --config backup_config.json --snapshot latest
```

### 9. Restore Snapshots

Reconstruct source data to a specified destination directory:

```bash
python main.py restore --snapshot latest --target ./restored_data
```

### 10. Manage Retention & Pruning

Enforce retention limits manually:

```bash
python main.py prune --config backup_config.json --keep 3
```

---

## Testing & Quality Assurance

Run the automated test suite with Python's built-in `unittest` (16 test cases):

```bash
python -m unittest discover -s tests -v
```

---

## License

This project is released under the MIT License.
