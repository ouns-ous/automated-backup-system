#!/usr/bin/env python3
"""
ByteVault Entry Point
Run automated file backups, verify integrity, restore snapshots, or manage retention.
"""

import sys
from automated_backup.cli import main

if __name__ == "__main__":
    sys.exit(main())
