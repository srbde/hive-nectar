import os
import unittest

from nectarstorage.sqlite import SQLiteStore


class MyStore(SQLiteStore):
    __tablename__ = "testing"
    __key__ = "key"
    __value__ = "value"

    defaults = {"default": "value"}


class Testcases(unittest.TestCase):
    def test_init(self):
        store = MyStore()
        self.assertEqual(store.storageDatabase, "nectar.sqlite")
        store = MyStore(profile="testing")
        self.assertEqual(store.storageDatabase, "testing.sqlite")

        directory = "/tmp/temporaryFolder"
        expected = os.path.join(directory, "testing.sqlite")

        store = MyStore(profile="testing", data_dir=directory)
        self.assertEqual(str(store.sqlite_file), expected)

    def test_initialdata(self):
        store = MyStore()
        store["foobar"] = "banana"
        self.assertEqual(store["foobar"], "banana")

        self.assertIsNone(store["empty"])

        self.assertEqual(store["default"], "value")
        self.assertEqual(len(store), 1)

    def test_permission_fallback(self):
        # We want to verify that when Path.mkdir raises a PermissionError,
        # the store falls back to an in-memory database and works normally.
        from pathlib import Path
        from unittest.mock import patch

        def mock_mkdir(self, *args, **kwargs):
            raise PermissionError("Permission denied")

        with patch.object(Path, "mkdir", mock_mkdir):
            store = MyStore(data_dir="/nonexistent/path/for/testing")
            # It should fall back to memory
            self.assertTrue(store.use_memory)
            self.assertEqual(store.sqlite_file, "file:nectar.sqlite?mode=memory&cache=shared")

            # The store should still be functional!
            store["foo"] = "bar"
            self.assertEqual(store["foo"], "bar")

    def test_write_permission_fallback(self):
        # The directory exists but writing to/creating the database fails.
        # We can simulate this by mocking sqlite3.connect to raise OperationalError
        # for standard files, but succeed for URI databases.
        import sqlite3
        from unittest.mock import patch

        original_connect = sqlite3.connect

        def mock_connect(database, *args, **kwargs):
            # If it's a standard path (not a memory URI), raise OperationalError
            if not database.startswith("file:"):
                raise sqlite3.OperationalError("unable to open database file")
            return original_connect(database, *args, **kwargs)

        import tempfile

        with patch("sqlite3.connect", mock_connect):
            with tempfile.TemporaryDirectory() as tmpdir:
                store = MyStore(data_dir=tmpdir)
                # Since standard connect raised an error, it should have fallen back to memory
                self.assertTrue(store.use_memory)
                self.assertEqual(store.sqlite_file, "file:nectar.sqlite?mode=memory&cache=shared")

                # The store should still be functional
                store["hello"] = "world"
                self.assertEqual(store["hello"], "world")

    def test_corrupt_file_fallback(self):
        # Issue #64: when the file exists but is not a valid SQLite database,
        # it should rename the corrupt file aside and fall back to memory.
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            corrupt_file = os.path.join(tmpdir, "nectar.sqlite")
            with open(corrupt_file, "wb") as f:
                f.write(b"this is not a valid sqlite database file")

            store = MyStore(data_dir=tmpdir)
            self.assertTrue(store.use_memory)
            self.assertEqual(store.sqlite_file, "file:nectar.sqlite?mode=memory&cache=shared")

            # Store should be functional
            store["key"] = "value"
            self.assertEqual(store["key"], "value")

            # Corrupt file should have been renamed aside
            self.assertFalse(os.path.exists(corrupt_file))
            files = os.listdir(tmpdir)
            self.assertTrue(any(".corrupted." in fname for fname in files))

    def test_corrupt_auxiliary_files_fallback(self):
        # Verify that auxiliary -wal and -shm files are also renamed aside
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            corrupt_file = os.path.join(tmpdir, "nectar.sqlite")
            wal_file = os.path.join(tmpdir, "nectar.sqlite-wal")
            shm_file = os.path.join(tmpdir, "nectar.sqlite-shm")

            with open(corrupt_file, "wb") as f:
                f.write(b"corrupt")
            with open(wal_file, "wb") as f:
                f.write(b"wal data")
            with open(shm_file, "wb") as f:
                f.write(b"shm data")

            store = MyStore(data_dir=tmpdir)
            self.assertTrue(store.use_memory)

            # Corrupt database and auxiliary files should no longer exist under original names
            self.assertFalse(os.path.exists(corrupt_file))
            self.assertFalse(os.path.exists(wal_file))
            self.assertFalse(os.path.exists(shm_file))

            files = os.listdir(tmpdir)
            self.assertTrue(any(".corrupted." in f for f in files))

    def test_runtime_database_error_fallback(self):
        # A store on disk that hits a DatabaseError at runtime falls back to memory
        import sqlite3
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            store = MyStore(data_dir=tmpdir)
            self.assertFalse(store.use_memory)

            original_connect = sqlite3.connect

            def mock_connect(database, *args, **kwargs):
                if not str(database).startswith("file:"):
                    raise sqlite3.DatabaseError("database disk image is malformed")
                return original_connect(database, *args, **kwargs)

            with patch("sqlite3.connect", mock_connect):
                store["runtime"] = "works"
                self.assertTrue(store.use_memory)
                self.assertEqual(store["runtime"], "works")
