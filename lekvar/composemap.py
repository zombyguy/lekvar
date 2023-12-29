from typing import Iterator, TypeVar
from collections.abc import MutableMapping, Mapping

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
