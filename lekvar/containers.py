from typing import Iterator, TypeVar, Any
from collections.abc import MutableMapping, Mapping, MutableSet

_KT = TypeVar("_KT")
_MT = TypeVar("_MT")
_VT = TypeVar("_VT")


class ComposeMap(Mapping):
    def __init__(self, dict_1: Mapping, dict_2: Mapping):
        super().__init__()
        self.dict_1 = dict_1
        self.dict_2 = dict_2

    def __getitem__(self, __key: _KT) -> _VT:
        return self.dict_2[self.dict_1[__key]]
    
    def __iter__(self) -> Iterator[_KT]:
        return self.dict_1.__iter__()

    def __len__(self) -> int:
        return self.dict_1.__len__()

    def __repr__(self) -> str:
        return "ComposeMap({" + \
                ', '.join([f"{repr(k)}: {repr(v)}" for k, v in self.items()]) \
                + "})"
        

class ComposeMutMap(ComposeMap):
    def __init__(self, dict_1: MutableMapping, dict_2: MutableMapping):
        super().__init__(dict_1, dict_2)
        self.dict_1: MutableMapping
        self.dict_2: MutableMapping

class noset(MutableSet):
    """
    Simple set-like class which doesn't retain any items.
    """
    # TODO: might be able to remove in_read with isinstance with this
    def __contains__(self, x: object) -> bool:
        return False
    def __len__(self) -> int:
        return 0
    def __iter__(self) -> Iterator:
        return zip()
    def add(self, value: Any) -> None:
        pass
    def discard(self, value: Any) -> None:
        pass
    def __repr__(self) -> str:
        return "noset()"
    def __str__(self) -> str:
        return "noset()"