"""
ByteVault Command Line Interface (CLI)
Provides command-line entry points for all backup, verification, restoration,
pruning, real-time watching, snapshot inspection, diffing, and dashboard generation.
"""

import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import sys
from typing import Optional

from automated_backup import __version__
from automated_backup.config import BackupConfig, create_default_config, load_config
from automated_backup.dashboard import DashboardGenerator
from automated_backup.doctor import BackupDoctor
from automated_backup.engine import BackupEngine
from automated_backup.history import FileHistoryEngine
from automated_backup.inspector import SnapshotInspector
from automated_backup.reporter import (
    format_bytes,
    print_backup_summary,
    print_snapshot_list,
)
from automated_backup.restore import RestoreEngine
from automated_backup.retention import RetentionManager
from automated_backup.watcher import BackupWatcher


def setup_logging(verbose: bool = False) -> None:
    """Configure console logging level and format."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def resolve_config(config_path_str: Optional[str]) -> BackupConfig:
    """Load config from path or fall back to default settings."""
    if config_path_str and Path(config_path_str).is_file():
        return load_config(Path(config_path_str))

    default_paths = [Path("backup_config.json"), Path("config.json")]
    for p in default_paths:
        if p.is_file():
            return load_config(p)

    return BackupConfig()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="bytevault",
        description="ByteVault - Automated Data & File Backup System"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: init
    init_parser = subparsers.add_parser("init", help="Initialize a template backup configuration file")
    init_parser.add_argument("-o", "--output", default="backup_config.json", help="Path for generated config file")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Execute backup job")
    run_parser.add_argument("-c", "--config", help="Path to JSON configuration file")
    run_parser.add_argument("--full", action="store_true", help="Force a full backup instead of incremental")
    run_parser.add_argument("--dry-run", action="store_true", help="Simulate backup without saving archives")
    run_parser.add_argument("--source", action="append", help="Override source directory (can repeat)")
    run_parser.add_argument("--dest", help="Override backup destination directory")

    # Command: list
    list_parser = subparsers.add_parser("list", help="List recorded snapshots")
    list_parser.add_argument("-c", "--config", help="Path to JSON configuration file")
    list_parser.add_argument("--dest", help="Override backup destination directory")

    # Command: verify
    verify_parser = subparsers.add_parser("verify", help="Verify snapshot integrity")
    verify_parser.add_argument("-s", "--snapshot", default="latest", help="Snapshot ID or 'latest'")
    verify_parser.add_argument("-c", "--config", help="Path to JSON configuration file")
    verify_parser.add_argument("--dest", help="Override backup destination directory")

    # Command: restore
    restore_parser = subparsers.add_parser("restore", help="Restore a snapshot to target directory")
    restore_parser.add_argument("-s", "--snapshot", default="latest", help="Snapshot ID or 'latest'")
    restore_parser.add_argument("-t", "--target", required=True, help="Destination directory for restored files")
    restore_parser.add_argument("-c", "--config", help="Path to JSON configuration file")
    restore_parser.add_argument("--dest", help="Override backup destination directory")
    restore_parser.add_argument("--no-verify", action="store_true", help="Skip checksum verification")
    restore_parser.add_argument("--include", action="append", help="Glob pattern of files to include (repeatable)")
    restore_parser.add_argument("--exclude", action="append", help="Glob pattern of files to exclude (repeatable)")
    restore_parser.add_argument("--skip-existing", action="store_true", help="Do not overwrite files already in target")
    restore_parser.add_argument("--dry-run", action="store_true", help="Preview restore plan without writing files")

    # Command: prune
    prune_parser = subparsers.add_parser("prune", help="Clean older snapshots according to retention policy")
    prune_parser.add_argument("-c", "--config", help="Path to JSON configuration file")
    prune_parser.add_argument("--keep", type=int, help="Number of snapshots to keep")
    prune_parser.add_argument("--days", type=int, help="Max age in days to retain")
    prune_parser.add_argument("--dry-run", action="store_true", help="Simulate pruning without deleting files")

    # Command: watch
    watch_parser = subparsers.add_parser("watch", help="Monitor sources and automatically back up on file changes")
    watch_parser.add_argument("-c", "--config", help="Path to JSON configuration file")
    watch_parser.add_argument("--interval", type=float, default=2.0, help="Poll interval in seconds")
    watch_parser.add_argument("--debounce", type=float, default=3.0, help="Debounce delay in seconds")
    watch_parser.add_argument("--cycles", type=int, help="Limit number of backup cycles before exiting")

    # Command: inspect
    inspect_parser = subparsers.add_parser("inspect", help="Inspect detailed file tree of a snapshot")
    inspect_parser.add_argument("-s", "--snapshot", default="latest", help="Snapshot ID or 'latest'")
    inspect_parser.add_argument("-c", "--config", help="Path to JSON configuration file")
    inspect_parser.add_argument("--dest", help="Override backup destination directory")

    # Command: diff
    diff_parser = subparsers.add_parser("diff", help="Diff two snapshots or diff live sources against a snapshot")
    diff_parser.add_argument("-s1", "--snap1", help="Base snapshot ID")
    diff_parser.add_argument("-s2", "--snap2", help="Target snapshot ID (optional if --live is used)")
    diff_parser.add_argument("--live", action="store_true", help="Diff current live source files against snapshot")
    diff_parser.add_argument("-c", "--config", help="Path to JSON configuration file")

    # Command: report
    report_parser = subparsers.add_parser("report", help="Generate an HTML dashboard or Markdown report")
    report_parser.add_argument("-c", "--config", help="Path to JSON configuration file")
    report_parser.add_argument("-o", "--output", default="backup_report.html", help="Output file path")
    report_parser.add_argument("-f", "--format", choices=["html", "markdown"], default="html", help="Report format")

    # Command: history
    history_parser = subparsers.add_parser("history", help="Inspect file revision history across snapshots or restore a single file version")
    history_parser.add_argument("pattern", help="File path or glob pattern (e.g. 'data.txt' or '*.py')")
    history_parser.add_argument("-c", "--config", help="Path to JSON configuration file")
    history_parser.add_argument("--dest", help="Override backup destination directory")
    history_parser.add_argument("--changes-only", action="store_true", help="Hide UNCHANGED snapshot entries")
    history_parser.add_argument("--restore-snapshot", help="Restore the specified file from this snapshot ID")
    history_parser.add_argument("-t", "--target", help="Target directory when using --restore-snapshot")

    # Command: dedupe
    dedupe_parser = subparsers.add_parser("dedupe", help="Analyze duplicate files and storage waste in a snapshot")
    dedupe_parser.add_argument("-s", "--snapshot", default="latest", help="Snapshot ID or 'latest'")
    dedupe_parser.add_argument("-c", "--config", help="Path to JSON configuration file")
    dedupe_parser.add_argument("--dest", help="Override backup destination directory")

    # Command: doctor
    doctor_parser = subparsers.add_parser("doctor", help="Audit vault health, archive checksums, incremental chains, and orphans")
    doctor_parser.add_argument("-c", "--config", help="Path to JSON configuration file")
    doctor_parser.add_argument("--dest", help="Override backup destination directory")
    doctor_parser.add_argument("--json", action="store_true", help="Output diagnostics report as JSON")

    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "init":
        out_path = Path(args.output)
        create_default_config(out_path)
        print(f"Created default configuration at: {out_path.resolve()}")
        return 0

    config = resolve_config(getattr(args, "config", None))
    if hasattr(args, "dest") and args.dest:
        config.backup_dest = args.dest
    if hasattr(args, "source") and args.source:
        config.source_dirs = args.source

    if args.command == "run":
        engine = BackupEngine(config)
        result = engine.run_backup(force_full=args.full, dry_run=args.dry_run)
        print_backup_summary(result)

        if not args.dry_run:
            retention = RetentionManager(config)
            prune_res = retention.prune_snapshots()
            if prune_res["pruned_count"] > 0:
                print(
                    f"Retention policy applied: pruned {prune_res['pruned_count']} snapshot(s), "
                    f"freed {format_bytes(prune_res['freed_bytes'])}."
                )
        return 0

    elif args.command == "list":
        engine = BackupEngine(config)
        snapshots = engine.get_existing_snapshots()
        print_snapshot_list(snapshots)
        return 0

    elif args.command == "verify":
        engine = BackupEngine(config)
        target_id = args.snapshot
        if target_id == "latest":
            latest = engine.get_latest_snapshot()
            if not latest:
                print("No snapshots available to verify.")
                return 1
            target_id = latest["snapshot_id"]

        result = engine.verify_snapshot(target_id)
        if result.get("valid"):
            print(f"Verification PASSED for snapshot: {target_id}")
            print(f"  Archive SHA-256: {result.get('archive_sha256')}")
            print(f"  Files Packed:    {result.get('files_packed')}")
            return 0
        else:
            print(f"Verification FAILED: {result.get('error')}")
            return 1

    elif args.command == "restore":
        dest_path = Path(config.backup_dest)
        restore_engine = RestoreEngine(dest_path)
        target_id = args.snapshot
        if target_id == "latest":
            backup_engine = BackupEngine(config)
            latest = backup_engine.get_latest_snapshot()
            if not latest:
                print("No snapshots available to restore.")
                return 1
            target_id = latest["snapshot_id"]

        target_dir = Path(args.target)
        result = restore_engine.restore(
            snapshot_id=target_id,
            target_dir=target_dir,
            verify_checksums=not args.no_verify,
            include_patterns=args.include,
            exclude_patterns=args.exclude,
            overwrite=not args.skip_existing,
            dry_run=args.dry_run,
        )

        if result.get("status") == "dry_run":
            print(f"[DRY RUN] Restore plan for snapshot {target_id} -> {target_dir}")
            print(f"  Planned files:  {result['restored_files_count']} ({format_bytes(result['total_bytes'])})")
            print(f"  Skipped files:  {result['skipped_count']}")
            for pf in result.get("planned_files", [])[:20]:
                print(f"    + {pf}")
            return 0
        elif result.get("status") == "success":
            print(f"Successfully restored snapshot {target_id} to {target_dir}")
            print(f"  Files restored: {result['restored_files_count']}")
            if result.get("skipped_count"):
                print(f"  Files skipped:  {result['skipped_count']}")
            print(f"  Total size:     {format_bytes(result['total_bytes'])}")
            print(f"  Integrity:      {'VERIFIED' if result['verified'] else 'SKIPPED'}")
            return 0
        else:
            print(f"Restoration issue detected! Corrupted files: {result.get('corrupted_files')}")
            return 1

    elif args.command == "prune":
        retention = RetentionManager(config)
        res = retention.prune_snapshots(
            retention_count=args.keep,
            retention_days=args.days,
            dry_run=args.dry_run
        )
        action_word = "Would prune" if args.dry_run else "Pruned"
        print(
            f"{action_word} {res['pruned_count']} snapshot(s). "
            f"Space freed: {format_bytes(res['freed_bytes'])}. "
            f"Retained: {res['retained_count']}."
        )
        if res["pruned_snapshots"]:
            print(f"Pruned snapshots: {', '.join(res['pruned_snapshots'])}")
        return 0

    elif args.command == "watch":
        watcher = BackupWatcher(config, debounce_seconds=args.debounce)
        print(f"ByteVault Watcher active. Monitoring {config.source_dirs}...")
        print(f"Press Ctrl+C to stop.")
        cycles = watcher.run_polling_loop(
            poll_interval=args.interval,
            max_cycles=args.cycles,
            on_backup_callback=lambda res: print(
                f"[{datetime.now().strftime('%H:%M:%S')}] Automated backup created: "
                f"{res.get('snapshot_id')} ({res.get('type')}) - "
                f"+{res.get('changes_summary', {}).get('added', 0)} added, "
                f"~{res.get('changes_summary', {}).get('modified', 0)} mod"
            )
        )
        print(f"Watcher exited after {cycles} backup cycle(s).")
        return 0

    elif args.command == "inspect":
        inspector = SnapshotInspector(config)
        data = inspector.inspect_snapshot(args.snapshot)
        print(f"\n=== Snapshot Inspection: {data['snapshot_id']} ===")
        print(f"Created: {data['timestamp']} | Type: {data['type'].upper()}")
        print(f"Archive: {data['archive_name']} ({format_bytes(data['archive_size_bytes'])})")
        print(f"Total Files: {data['files_count']} ({format_bytes(data['total_uncompressed_bytes'])})\n")
        print(f"{'File Path':<40} {'Size':<10} {'Origin Snapshot'}")
        print("-" * 75)
        for f in data["files"]:
            print(f"{f['path']:<40} {format_bytes(f['size']):<10} {f['origin_snapshot']}")
        print()
        return 0

    elif args.command == "diff":
        inspector = SnapshotInspector(config)
        if args.live:
            base = args.snap1 or "latest"
            res = inspector.diff_live(base)
            print(f"\n=== Live Diff vs Snapshot: {res['compared_against_snapshot']} ===")
            print(f"Pending backup size: {format_bytes(res['pending_backup_bytes'])}")
        else:
            if not args.snap1 or not args.snap2:
                print("Error: Specify both -s1 and -s2, or use --live to compare against current files.")
                return 1
            res = inspector.diff_snapshots(args.snap1, args.snap2)
            print(f"\n=== Snapshot Diff: {res['base_snapshot']} -> {res['target_snapshot']} ===")
            print(f"Net size delta: {format_bytes(res['size_delta_bytes'])}")

        print(f"Added:    {len(res['added'])} {res['added'][:5] if res['added'] else ''}")
        print(f"Modified: {len(res['modified'])} {res['modified'][:5] if res['modified'] else ''}")
        print(f"Deleted:  {len(res['deleted'])} {res['deleted'][:5] if res['deleted'] else ''}")
        print(f"Unchanged count: {res['unchanged_count']}\n")
        return 0

    elif args.command == "report":
        gen = DashboardGenerator(config)
        out = gen.export(Path(args.output), fmt=args.format)
        print(f"Dashboard report successfully exported to: {out}")
        return 0

    elif args.command == "history":
        history_engine = FileHistoryEngine(config)
        if args.restore_snapshot:
            if not args.target:
                print("Error: --target is required when using --restore-snapshot.")
                return 1
            res = history_engine.restore_file_version(
                file_path=args.pattern,
                snapshot_id=args.restore_snapshot,
                target_dir=Path(args.target),
            )
            print(
                f"Restored '{args.pattern}' from {res['snapshot_id']} to {res['target_dir']} "
                f"({format_bytes(res['total_bytes'])}, verified={res['verified']})"
            )
            return 0 if res.get("status") == "success" else 1

        hist = history_engine.get_file_history(args.pattern, changes_only=args.changes_only)
        print(f"\n=== File History: '{hist['pattern']}' ({hist['matched_files_count']} file(s) across {hist['snapshots_scanned']} snapshot(s)) ===")
        if not hist["files"]:
            print("No matching files found in snapshot history.\n")
            return 0
        for path, timeline in hist["files"].items():
            print(f"\nFile: {path}")
            for entry in timeline:
                sha_short = (entry["sha256"] or "-")[:12]
                ts = (entry["timestamp"] or "N/A")[:19].replace("T", " ")
                print(
                    f"  [{entry['status']:<9}] {ts} | {entry['snapshot_id']} | "
                    f"{format_bytes(entry['size']):<10} | sha256:{sha_short}"
                )
        print()
        return 0

    elif args.command == "dedupe":
        history_engine = FileHistoryEngine(config)
        res = history_engine.find_duplicate_files(snapshot_id=args.snapshot)
        print(f"\n=== Duplicate Analysis: {res['snapshot_id']} ===")
        print(f"Total Files Scanned:   {res['total_files']}")
        print(f"Duplicate Groups:      {res['duplicate_groups_count']}")
        print(f"Total Duplicate Files: {res['total_duplicate_files']}")
        print(f"Reclaimable Waste:     {format_bytes(res['wasted_bytes'])}\n")
        for group in res["groups"]:
            print(f"  SHA-256 {group['sha256'][:16]}... ({format_bytes(group['size'])} x {group['count']}):")
            for p in group["paths"]:
                print(f"    - {p}")
        return 0

    elif args.command == "doctor":
        doc = BackupDoctor(config)
        diag = doc.run_diagnostics()
        if args.json:
            print(json.dumps(diag, indent=2))
        else:
            print(f"\n=== ByteVault Doctor Report: {diag['task_name']} ===")
            print(f"Health Status:      {diag['health_status']}")
            print(f"Snapshots Checked:  {diag['valid_snapshots']} / {diag['total_snapshots']} valid")
            print(f"Corrupt Snapshots:  {len(diag['corrupt_snapshots'])}")
            print(f"Broken Chains:      {len(diag['broken_chains'])}")
            print(f"Orphaned Archives:  {len(diag['orphaned_archives'])}")
            print(f"Orphaned Manifests: {len(diag['orphaned_manifests'])}")
            dup = diag["duplicate_summary"]
            print(f"Duplicate Waste:    {format_bytes(dup['wasted_bytes'])} ({dup['duplicate_groups_count']} group(s))\n")
        return 0 if diag["health_status"] != "CRITICAL" else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
