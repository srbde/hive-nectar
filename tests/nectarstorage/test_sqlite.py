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

        with patch("sqlite3.connect", mock_connect):
            store = MyStore(data_dir="/tmp/test_nonexistent_writable")
            # Since standard connect raised an error, it should have fallen back to memory
            self.assertTrue(store.use_memory)
            self.assertEqual(store.sqlite_file, "file:nectar.sqlite?mode=memory&cache=shared")

            # The store should still be functional
            store["hello"] = "world"
            self.assertEqual(store["hello"], "world")
