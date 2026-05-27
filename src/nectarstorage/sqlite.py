# Inspired by https://raw.githubusercontent.com/xeroc/python-graphenelib/master/graphenestorage/sqlite.py
import logging
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Tuple, Union

from appdirs import user_data_dir

from .interfaces import StoreInterface

log = logging.getLogger(__name__)
timeformat = "%Y%m%d-%H%M%S"


class SQLiteFile:
    """This class ensures that the user's data is stored in its OS
    preotected user directory:

    **OSX:**

     * `~/Library/Application Support/<AppName>`

    **Windows:**

     * `C:\\Documents and Settings\\<User>\\Application Data\\Local Settings\\<AppAuthor>\\<AppName>`
     * `C:\\Documents and Settings\\<User>\\Application Data\\<AppAuthor>\\<AppName>`

    **Linux:**

     * `~/.local/share/<AppName>`

     Furthermore, it offers an interface to generated backups
     in the `backups/` directory every now and then.

     .. note:: The file name can be overwritten when providing a keyword
        argument ``profile``.
    """

    data_dir: Path
    storageDatabase: str
    sqlite_file: Union[Path, str]
    use_memory: bool

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        appauthor = "nectar"
        appname = kwargs.get("appname", "nectar")
        self.data_dir = Path(kwargs.get("data_dir", user_data_dir(appname, appauthor)))

        if "profile" in kwargs:
            self.storageDatabase = f"{kwargs['profile']}.sqlite"
        else:
            self.storageDatabase = f"{appname}.sqlite"

        self.use_memory = False
        try:
            if not self.data_dir.is_dir():  # pragma: no cover
                self.data_dir.mkdir(parents=True)
            self.sqlite_file = self.data_dir / self.storageDatabase
        except (OSError, PermissionError) as e:  # pragma: no cover
            self.use_memory = True
            self.sqlite_file = f"file:{self.storageDatabase}?mode=memory&cache=shared"
            log.warning(
                f"Could not create storage directory {self.data_dir} ({e}). "
                f"Falling back to in-memory SQLite database: {self.sqlite_file}"
            )

    def sqlite3_backup(self, backupdir: Union[str, Path]) -> None:
        """Create timestamped database copy"""
        if getattr(self, "use_memory", False):
            return
        backup_path = Path(backupdir)
        if not backup_path.is_dir():
            backup_path.mkdir()
        backup_file = backup_path / (
            f"{Path(self.storageDatabase).stem}-{datetime.now(timezone.utc).strftime(timeformat)}"
        )
        self.sqlite3_copy(self.sqlite_file, backup_file)

    def sqlite3_copy(self, src: Union[Path, str], dst: Union[Path, str]) -> None:
        """Copy sql file from src to dst"""
        if getattr(self, "use_memory", False):
            return
        src_path = Path(src)
        if not src_path.is_file():
            return
        connection = sqlite3.connect(str(self.sqlite_file))
        try:
            cursor = connection.cursor()
            # Lock database before making a backup
            cursor.execute("begin immediate")
            # Make new backup file
            shutil.copyfile(str(src), str(dst))
            log.info(f"Creating {dst}...")
            # Unlock database
            connection.rollback()
        finally:
            connection.close()

    def recover_with_latest_backup(self, backupdir: Union[str, Path] = "backups") -> None:
        """Replace database with latest backup"""
        if getattr(self, "use_memory", False):
            return
        file_date = 0
        backup_path = Path(backupdir)
        if not backup_path.is_dir():
            # Treat string backupdir as relative to data_dir
            backup_path = self.data_dir / str(backupdir)
        if not backup_path.is_dir():
            return
        newest_backup_file = None
        for backup_file in backup_path.iterdir():
            if backup_file.stat().st_ctime > file_date:
                if backup_file.is_file():
                    file_date = backup_file.stat().st_ctime
                    newest_backup_file = backup_file
        if newest_backup_file is not None:
            self.sqlite3_copy(newest_backup_file, self.sqlite_file)

    def clean_data(self, backupdir: Union[str, Path] = "backups") -> None:
        """Delete files older than 70 days"""
        if getattr(self, "use_memory", False):
            return
        log.info("Cleaning up old backups")
        # Allow either a Path or a directory name relative to data_dir
        backup_path = Path(backupdir)
        if not backup_path.is_dir():
            backup_path = self.data_dir / str(backupdir)
        if not backup_path.is_dir():
            return
        for backup_file in backup_path.iterdir():
            if backup_file.stat().st_ctime < (time.time() - 70 * 86400):
                if backup_file.is_file():
                    backup_file.unlink()
                    log.info(f"Deleting {backup_file}...")

    def refreshBackup(self) -> None:
        """Make a new backup"""
        if getattr(self, "use_memory", False):
            return
        backupdir = self.data_dir / "backups"
        self.sqlite3_backup(backupdir)
        # Clean by logical name so clean_data resolves under data_dir correctly
        self.clean_data("backups")


class SQLiteCommon:
    """This class abstracts away common sqlite3 operations.

    This class should not be used directly.

    When inheriting from this class, the following instance members must
    be defined:

        * ``sqlite_file``: Path to the SQLite Database file
    """

    sqlite_file: Union[Path, str]
    use_memory: bool

    def sql_fetchone(self, query: Tuple[str, Tuple]) -> Optional[Tuple]:
        connection = sqlite3.connect(str(self.sqlite_file), uri=getattr(self, "use_memory", False))
        try:
            cursor = connection.cursor()
            cursor.execute(*query)
            result = cursor.fetchone()
        finally:
            connection.close()
        return result

    def sql_fetchall(self, query: Tuple[str, Tuple]) -> list:
        connection = sqlite3.connect(str(self.sqlite_file), uri=getattr(self, "use_memory", False))
        try:
            cursor = connection.cursor()
            cursor.execute(*query)
            results = cursor.fetchall()
        finally:
            connection.close()
        return results

    def sql_execute(self, query: Tuple[str, Tuple], lastid: bool = False) -> Optional[int]:
        connection = sqlite3.connect(str(self.sqlite_file), uri=getattr(self, "use_memory", False))
        try:
            cursor = connection.cursor()
            cursor.execute(*query)
            connection.commit()
        except Exception:
            connection.close()
            raise
        ret = None
        try:
            if lastid:
                cursor = connection.cursor()
                cursor.execute("SELECT last_insert_rowid();")
                ret = cursor.fetchone()[0]
        finally:
            connection.close()
        return ret


class SQLiteStore(SQLiteFile, SQLiteCommon, StoreInterface):
    """The SQLiteStore deals with the sqlite3 part of storing data into a
    database file.

    .. note:: This module is limited to two columns and merely stores
        key/value pairs into the sqlite database

    On first launch, the database file as well as the tables are created
    automatically.

    When inheriting from this class, the following three class members must
    be defined:

        * ``__tablename__``: Name of the table
        * ``__key__``: Name of the key column
        * ``__value__``: Name of the value column
    """

    #:
    __tablename__ = None
    __key__ = None
    __value__ = None

    def __init__(self, *args, **kwargs):
        #: Storage
        SQLiteFile.__init__(self, *args, **kwargs)
        StoreInterface.__init__(self, *args, **kwargs)
        if self.__tablename__ is None or self.__key__ is None or self.__value__ is None:
            raise ValueError("Values missing for tablename, key, or value!")

        if getattr(self, "use_memory", False):
            self._keep_alive = sqlite3.connect(str(self.sqlite_file), uri=True)

        try:
            if not self.exists():  # pragma: no cover
                self.create()
        except (sqlite3.OperationalError, OSError) as e:
            log.warning(
                f"Database connection or creation failed for file {self.sqlite_file}: {e}. "
                "Falling back to an in-memory SQLite database."
            )
            self.use_memory = True
            self.sqlite_file = f"file:{self.storageDatabase}?mode=memory&cache=shared"
            self._keep_alive = sqlite3.connect(str(self.sqlite_file), uri=True)
            if not self.exists():
                self.create()

    def _haveKey(self, key: str) -> bool:
        """Is the key `key` available?"""
        query = (
            f"SELECT {self.__value__} FROM {self.__tablename__} WHERE {self.__key__}=?",
            (key,),
        )
        return True if self.sql_fetchone(query) else False

    def __setitem__(self, key: str, value: str) -> None:
        """Sets an item in the store

        :param str key: Key
        :param str value: Value
        """
        if self._haveKey(key):
            query = (
                f"UPDATE {self.__tablename__} SET {self.__value__}=? WHERE {self.__key__}=?",
                (value, key),
            )
        else:
            query = (
                f"INSERT INTO {self.__tablename__} ({self.__key__}, {self.__value__}) VALUES (?, ?)",
                (key, value),
            )
        self.sql_execute(query)

    def __getitem__(self, key: str) -> Optional[str]:
        """Gets an item from the store as if it was a dictionary

        :param str value: Value
        """
        query = (
            f"SELECT {self.__value__} FROM {self.__tablename__} WHERE {self.__key__}=?",
            (key,),
        )
        result = self.sql_fetchone(query)
        if result:
            return result[0]
        else:
            if key in self.defaults:
                return self.defaults[key]
            else:
                return None

    def __iter__(self):
        """Iterates through the store"""
        return iter(self.keys())

    def keys(self):
        query = (f"SELECT {self.__key__} from {self.__tablename__}", ())
        key_list = [x[0] for x in self.sql_fetchall(query)]
        return dict.fromkeys(key_list).keys()

    def __len__(self) -> int:
        """return lenght of store"""
        query = (f"SELECT id from {self.__tablename__}", ())
        return len(self.sql_fetchall(query))

    def __contains__(self, key: object) -> bool:
        """Tests if a key is contained in the store.

        May test againsts self.defaults

        :param str value: Value
        """
        key_str = str(key)
        if self._haveKey(key_str) or key_str in self.defaults:
            return True
        else:
            return False

    def items(self):
        """returns all items off the store as tuples"""
        query = (f"SELECT {self.__key__}, {self.__value__} from {self.__tablename__}", ())
        collected = {key: value for key, value in self.sql_fetchall(query)}
        return collected.items()

    def get(self, key: str, default: Any = None) -> Any:
        """Return the key if exists or a default value

        :param str value: Value
        :param str default: Default value if key not present
        """
        if key in self:
            return self.__getitem__(key)
        else:
            return default

    # Specific for this library
    def delete(self, key: str) -> None:
        """Delete a key from the store

        :param str value: Value
        """
        query = (
            f"DELETE FROM {self.__tablename__} WHERE {self.__key__}=?",
            (key,),
        )
        self.sql_execute(query)

    def wipe(self) -> None:
        """Wipe the store"""
        query = (f"DELETE FROM {self.__tablename__}", ())
        self.sql_execute(query)

    def exists(self) -> bool:
        """Check if the database table exists"""
        query = (
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (self.__tablename__,),
        )
        return True if self.sql_fetchone(query) else False

    def create(self) -> None:  # pragma: no cover
        """Create the new table in the SQLite database"""
        query = (
            f"""
            CREATE TABLE {self.__tablename__} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {self.__key__} STRING(256),
                {self.__value__} STRING(256)
            )""",
            (),
        )
        self.sql_execute(query)
