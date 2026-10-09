"""
Tests for Hasher and Manifest utilities.
"""

import hashlib
from pathlib import Path
import tempfile
import unittest

from automated_backup.hasher import (
    calculate_file_hash,
    compare_manifests,
    is_excluded,
    scan_source,
)


class TestHasher(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_calculate_file_hash(self):
        test_file = self.root / "hello.txt"
        content = b"Hello, ByteVault World!"
        test_file.write_bytes(content)

        expected = hashlib.sha256(content).hexdigest()
        actual = calculate_file_hash(test_file)
        self.assertEqual(actual, expected)

    def test_is_excluded(self):
        patterns = ["*.tmp", "cache/*", "*/__pycache__/*", ".git/*"]

        self.assertTrue(is_excluded("file.tmp", patterns))
        self.assertTrue(is_excluded("deep/path/file.tmp", patterns))
        self.assertTrue(is_excluded("cache/data.bin", patterns))
        self.assertTrue(is_excluded("foo/__pycache__/mod.cpython-310.pyc", patterns))
        self.assertTrue(is_excluded(".git/config", patterns))

        self.assertFalse(is_excluded("document.pdf", patterns))
        self.assertFalse(is_excluded("src/main.py", patterns))

    def test_scan_source(self):
        (self.root / "doc1.txt").write_text("document one", encoding="utf-8")
        sub = self.root / "subfolder"
        sub.mkdir()
        (sub / "doc2.txt").write_text("document two", encoding="utf-8")
        (sub / "scratch.tmp").write_text("temp data", encoding="utf-8")

        manifest = scan_source(self.root, exclude_patterns=["*.tmp"])

        self.assertIn("doc1.txt", manifest)
        self.assertIn("subfolder/doc2.txt", manifest)
        self.assertNotIn("subfolder/scratch.tmp", manifest)
        self.assertIsNotNone(manifest["doc1.txt"]["sha256"])

    def test_compare_manifests(self):
        old_manifest = {
            "file_a.txt": {"size": 10, "sha256": "hash_a", "mtime": 100},
            "file_b.txt": {"size": 20, "sha256": "hash_b_old", "mtime": 100},
            "file_c.txt": {"size": 30, "sha256": "hash_c", "mtime": 100},
        }

        new_manifest = {
            "file_a.txt": {"size": 10, "sha256": "hash_a", "mtime": 100},  # unchanged
            "file_b.txt": {"size": 25, "sha256": "hash_b_new", "mtime": 150},  # modified
            "file_d.txt": {"size": 40, "sha256": "hash_d", "mtime": 150},  # added
            # file_c.txt was deleted
        }

        diff = compare_manifests(old_manifest, new_manifest)
        self.assertEqual(diff["added"], ["file_d.txt"])
        self.assertEqual(diff["modified"], ["file_b.txt"])
        self.assertEqual(diff["deleted"], ["file_c.txt"])
        self.assertEqual(diff["unchanged"], ["file_a.txt"])


if __name__ == "__main__":
    unittest.main()
