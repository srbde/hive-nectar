import json
from typing import Any

from nectargraphenebase.types import Id, JsonObj, Optional, String

from .operationids import operations


class Operation:
    def __init__(self, op: list[Any] | dict[str, Any] | Any) -> None:
        if isinstance(op, list) and len(op) == 2:
            if isinstance(op[0], int):
                self.opId = op[0]
                name = self.getOperationNameForId(self.opId)
            else:
                self.opId = self.operations().get(op[0], None)
                name = op[0]
                if self.opId is None:
                    raise ValueError("Unknown operation")
            self.name = name[0].upper() + name[1:]  # klassname
            try:
                klass = self._getklass(self.name)
            except Exception:
                raise NotImplementedError("Unimplemented Operation %s" % self.name)
            self.op = klass(op[1])
            self.appbase = False
        elif isinstance(op, dict):
            if len(op["type"]) > 10 and op["type"][-9:] == "operation":
                name = op["type"][:-10]
            else:
                name = op["type"]
            self.opId = self.operations().get(name, None)
            if self.opId is None:
                raise ValueError("Unknown operation")
            self.name = name[0].upper() + name[1:]  # klassname
            try:
                klass = self._getklass(self.name)
            except Exception:
                raise NotImplementedError("Unimplemented Operation %s" % self.name)
            self.op = klass(op["value"])
            self.appbase = True
        else:
            self.op = op
            self.name = type(self.op).__name__.lower()  # also store name
            self.opId = self.operations()[self.name]

    def operations(self) -> dict[str, int]:
        return operations

    def getOperationNameForId(self, i: int) -> str:
        """Convert an operation id into the corresponding string"""
        for key in self.operations():
            if int(self.operations()[key]) is int(i):
                return key
        return "Unknown Operation ID %d" % i

    def _getklass(self, name: str) -> type:
        module = __import__("graphenebase.operations", fromlist=["operations"])
        class_ = getattr(module, name)
        return class_

    def __bytes__(self) -> bytes:
        if self.opId is None:
            raise ValueError("Operation ID is None, cannot serialize operation")
        return bytes(Id(self.opId)) + bytes(self.op)

    def __str__(self) -> str:
        # Try to get JSON data from operation, fallback to raw object if toJson not available
        # This handles both GrapheneObject instances (with toJson) and raw data
        try:
            op_data = self.op.toJson()  # type: ignore[attr-defined]
        except (AttributeError, TypeError):
            op_data = self.op
        return json.dumps([self.opId, op_data])


class GrapheneObject:
    """Core abstraction class

    This class is used for any JSON reflected object in Graphene.

    * ``instance.__json__()``: encodes data into json format
    * ``bytes(instance)``: encodes data into wire format
    * ``str(instances)``: dumps json object as string

    """

    def __init__(self, data: Any = None) -> None:
        self.data = data

    def __bytes__(self) -> bytes:
        if self.data is None:
            return b""
        b = b""
        for name, value in list(self.data.items()):
            if isinstance(value, str):
                b += bytes(value, "utf-8")
            else:
                b += bytes(value)
        return b

    def __json__(self) -> dict[str, Any]:
        if self.data is None:
            return {}
        d = {}  # JSON output is *not* ordered
        for name, value in list(self.data.items()):
            if isinstance(value, Optional) and value.isempty():
                continue

            if isinstance(value, String):
                d.update({name: str(value)})
            else:
                try:
                    d.update({name: JsonObj(value)})
                except Exception:
                    d.update({name: value.__str__()})
        return d

    def __str__(self) -> str:
        return json.dumps(self.__json__())

    def toJson(self) -> dict[str, Any]:
        return self.__json__()

    def json(self) -> dict[str, Any]:
        return self.__json__()


def isArgsThisClass(self: Any, args: tuple) -> bool:
    return len(args) == 1 and type(args[0]).__name__ == type(self).__name__
