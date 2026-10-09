"""
ByteVault Reporter Module
Formats backup, verification, and restoration results for console display and logs.
"""

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def format_bytes(num_bytes: int) -> str:
    """Format bytes into human-readable string (KB, MB, GB)."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    for unit in ["KB", "MB", "GB", "TB"]:
        num_bytes /= 1024.0
        if num_bytes < 1024:
            return f"{num_bytes:.2f} {unit}"
    return f"{num_bytes:.2f} PB"


def print_backup_summary(result: Dict[str, Any]) -> None:
    """Print formatted summary of a backup operation."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()
        status_color = "green" if result.get("status") == "success" else "yellow"

        table = Table(show_header=False, box=None)
        table.add_row("[bold]Status:[/bold]", f"[{status_color}]{result.get('status', 'N/A').upper()}[/{status_color}]")
        table.add_row("[bold]Snapshot ID:[/bold]", result.get("snapshot_id", "N/A"))
        table.add_row("[bold]Type:[/bold]", result.get("type", "N/A").upper())
        table.add_row("[bold]Files Packed:[/bold]", str(result.get("files_packed_count", result.get("files_to_pack_count", 0))))
        table.add_row("[bold]Packed Size:[/bold]", format_bytes(result.get("packed_bytes", result.get("total_bytes", 0))))
        if "archive_size_bytes" in result:
            table.add_row("[bold]Archive Size:[/bold]", format_bytes(result.get("archive_size_bytes", 0)))
        if "archive_sha256" in result:
            table.add_row("[bold]Archive SHA-256:[/bold]", f"[cyan]{result.get('archive_sha256')[:16]}...[/cyan]")

        changes = result.get("changes_summary", {})
        table.add_row(
            "[bold]Changes:[/bold]",
            f"+{changes.get('added', 0)} added, ~{changes.get('modified', 0)} modified, -{changes.get('deleted', 0)} deleted"
        )
        table.add_row("[bold]Duration:[/bold]", f"{result.get('duration_seconds', 0)}s")

        console.print(Panel(table, title="[bold cyan]ByteVault Backup Result[/bold cyan]", expand=False))
    except ImportError:
        print("\n================ BYTEVAULT BACKUP RESULT ================")
        print(f"Status:       {result.get('status', 'N/A').upper()}")
        print(f"Snapshot ID:  {result.get('snapshot_id', 'N/A')}")
        print(f"Type:         {result.get('type', 'N/A').upper()}")
        print(f"Files Packed: {result.get('files_packed_count', result.get('files_to_pack_count', 0))}")
        print(f"Packed Size:  {format_bytes(result.get('packed_bytes', result.get('total_bytes', 0)))}")
        if "archive_size_bytes" in result:
            print(f"Archive Size: {format_bytes(result.get('archive_size_bytes', 0))}")
        changes = result.get("changes_summary", {})
        print(f"Changes:      +{changes.get('added', 0)} added, ~{changes.get('modified', 0)} mod, -{changes.get('deleted', 0)} del")
        print(f"Duration:     {result.get('duration_seconds', 0)}s")
        print("=========================================================\n")


def print_snapshot_list(snapshots: List[Dict[str, Any]]) -> None:
    """Print tabular list of recorded snapshots."""
    if not snapshots:
        print("No snapshots found.")
        return

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Recorded Snapshots", show_lines=True)
        table.add_column("Snapshot ID", style="cyan", no_wrap=True)
        table.add_column("Type", style="magenta")
        table.add_column("Timestamp", style="dim")
        table.add_column("Files", justify="right")
        table.add_column("Archive Size", justify="right")
        table.add_column("Base Snapshot", style="dim")

        for s in snapshots:
            table.add_row(
                s.get("snapshot_id", "N/A"),
                s.get("type", "N/A").upper(),
                s.get("timestamp", "N/A")[:19],
                str(s.get("files_packed_count", 0)),
                format_bytes(s.get("archive_size_bytes", 0)),
                s.get("base_snapshot_id") or "None (Full)",
            )
        console.print(table)
    except ImportError:
        print(f"{'Snapshot ID':<35} {'Type':<6} {'Files':<6} {'Archive Size':<12} {'Base'}")
        print("-" * 75)
        for s in snapshots:
            print(
                f"{s.get('snapshot_id', 'N/A'):<35} "
                f"{s.get('type', 'N/A').upper():<6} "
                f"{s.get('files_packed_count', 0):<6} "
                f"{format_bytes(s.get('archive_size_bytes', 0)):<12} "
                f"{s.get('base_snapshot_id') or '-'}"
            )
