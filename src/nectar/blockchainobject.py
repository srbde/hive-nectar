import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from nectar.instance import shared_blockchain_instance


class ObjectCache(dict):
    def __init__(
        self,
        initial_data: dict[Any, Any] | None = None,
        default_expiration: int = 10,
        auto_clean: bool = True,
    ) -> None:
        super().__init__(initial_data or {})
        self.set_expiration(default_expiration)
        self.auto_clean = auto_clean
        self.lock = threading.RLock()

    def __setitem__(self, key: Any, value: Any) -> None:
        data = {
            "expires": datetime.now(timezone.utc) + timedelta(seconds=self.default_expiration),
            "data": value,
        }
        with self.lock:
            if key in self:
                del self[key]
            dict.__setitem__(self, key, data)
        if self.auto_clean:
            self.clear_expired_items()

    def __getitem__(self, key: Any) -> Any:
        with self.lock:
            if key in self:
                value = dict.__getitem__(self, key)
                if value is not None:
                    return value["data"]

    def get(self, key: Any, default: Any = None) -> Any:
        with self.lock:
            if key in self:
                if self[key] is not None:
                    return self[key]
                else:
                    return default
            else:
                return default

    def clear_expired_items(self) -> None:
        with self.lock:
            del_list = []
            utc_now = datetime.now(timezone.utc)
            for key in self:
                value = dict.__getitem__(self, key)
                if value is None:
                    del_list.append(key)
                    continue
                if utc_now >= value["expires"]:
                    del_list.append(key)
            for key in del_list:
                del self[key]

    def __contains__(self, key: Any) -> bool:
        with self.lock:
            if dict.__contains__(self, key):
                value = dict.__getitem__(self, key)
                if value is None:
                    return False
                if datetime.now(timezone.utc) < value["expires"]:
                    return True
                else:
                    value["data"] = None
            return False

    def __str__(self) -> str:
        if self.auto_clean:
            self.clear_expired_items()
        n = 0
        with self.lock:
            n = len(list(self.keys()))
        return f"ObjectCache(n={n}, default_expiration={self.default_expiration})"

    def set_expiration(self, expiration: int) -> None:
        """Set new default expiration time in seconds (default: 10s)"""
        self.default_expiration = expiration


class BlockchainObject(dict):
    space_id = 1
    type_id = None
    type_ids = []

    _cache = ObjectCache()

    def __init__(
        self,
        data: dict[str, Any] | int | str | Any,
        klass: type | None = None,
        space_id: int = 1,
        object_id: Any | None = None,
        lazy: bool = False,
        use_cache: bool = True,
        id_item: str | None = None,
        blockchain_instance: Any | None = None,
        *args,
        **kwargs,
    ) -> None:
        """
        Initialize a BlockchainObject, setting its identifier and optionally loading or caching its data.

        This constructor accepts a variety of `data` forms:
        - dict or instance of `klass`: uses the mapping directly as the object's data.
        - int: treated as a block number (identifier) and stored under `id_item`.
        - str: treated as an object identifier string and stored under `id_item`.
        - other scalar identifiers: validated with test_valid_objectid and may trigger a lookup.

        Behavioral notes:
        - If `lazy` is False the constructor may call refresh() to populate the object from the blockchain.
        - If `use_cache` is True and not lazy, the object will be stored in the class-level cache and marked as cached.
        - Raises ValueError if `data` is a list, set, or tuple (these collection types are not supported).

        Parameters:
            data: dict, instance, int, str, or identifier
                The source for the object's data or its identifier.
            klass (optional): type
                If provided and `data` is an instance of this type, the instance's mapping is used directly.
            space_id (int, optional):
                Numeric namespace for the object type (defaults to 1).
            object_id (optional):
                Explicit object id value — kept for callers that supply it but not otherwise interpreted by the constructor.
            lazy (bool, optional):
                If True, defer loading object contents (do not call refresh()).
            use_cache (bool, optional):
                If True and not lazy, store the constructed object in the class cache.
            id_item (str, optional):
                Key name used to read/write the object's identifier in the underlying mapping (defaults to "id").

        Raises:
            ValueError: if `data` is a list, set, or tuple.
        """
        self.blockchain = blockchain_instance or shared_blockchain_instance()
        self.cached = False
        self.identifier = None

        # We don't read lists, sets, or tuples
        if isinstance(data, (list, set, tuple)):
            raise ValueError("Cannot interpret lists! Please load elements individually!")

        if id_item and isinstance(id_item, str):
            self.id_item = id_item
        else:
            self.id_item = "id"
        if klass and isinstance(data, klass) and hasattr(data, "get"):
            mapping_data = cast(dict[str, Any], data)
            self.identifier = mapping_data.get(self.id_item)
            super().__init__(mapping_data)
        elif isinstance(data, dict):
            mapping_data = cast(dict[str, Any], data)
            self.identifier = mapping_data.get(self.id_item)
            super().__init__(mapping_data)
        elif isinstance(data, int):
            # This is only for block number basically
            self.identifier = data
            if not lazy and not self.cached:
                self.refresh()
            # make sure to store the blocknumber for caching
            self[self.id_item] = data
            # Set identifier again as it is overwritten in super() in refresh()
            self.identifier = data
        elif isinstance(data, str):
            self.identifier = data
            if not lazy and not self.cached:
                self.refresh()
            self[self.id_item] = str(data)
            self.identifier = data
        else:
            self.identifier = data
            if self.test_valid_objectid(self.identifier):
                # Here we assume we deal with an id
                self.testid(self.identifier)
            if self.iscached(data):
                super().__init__(self.getcache(data))
            elif not lazy and not self.cached:
                self.refresh()

        if use_cache and not lazy:
            self.cache()
            self.cached = True

    def refresh(self) -> None:
        """Refresh the object's data from the API.

        This method should be overridden by subclasses to implement
        specific refresh logic. The base implementation does nothing.
        """
        pass

    @staticmethod
    def clear_cache() -> None:
        BlockchainObject._cache = ObjectCache()

    def test_valid_objectid(self, i: Any) -> bool:
        if isinstance(i, str):
            return True
        elif isinstance(i, int):
            return True
        else:
            return False

    def testid(self, id: Any) -> None:
        if not self.type_id:
            return

        if not self.type_ids:
            self.type_ids = [self.type_id]

    def cache(self) -> None:
        # store in cache
        if dict.__contains__(self, self.id_item):
            BlockchainObject._cache[self.get(self.id_item)] = self

    def clear_cache_from_expired_items(self) -> None:
        BlockchainObject._cache.clear_expired_items()

    def set_cache_expiration(self, expiration: int) -> None:
        BlockchainObject._cache.default_expiration = expiration

    def set_cache_auto_clean(self, auto_clean: bool) -> None:
        BlockchainObject._cache.auto_clean = auto_clean

    def get_cache_expiration(self) -> int:
        return BlockchainObject._cache.default_expiration

    def get_cache_auto_clean(self) -> bool:
        return BlockchainObject._cache.auto_clean

    def iscached(self, id: Any) -> bool:
        return id in BlockchainObject._cache

    def getcache(self, id: Any) -> Any:
        return BlockchainObject._cache.get(id, None)

    def __getitem__(self, key: Any) -> Any:
        if not self.cached:
            self.refresh()
        return super().__getitem__(key)

    def items(self):
        if not self.cached:
            self.refresh()
        return super().items()

    def __contains__(self, key: Any) -> bool:
        if not self.cached:
            self.refresh()
        return super().__contains__(key)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {str(self.identifier)}>"

    def json(self) -> dict[str, Any]:
        return json.loads(str(json.dumps(self)))
