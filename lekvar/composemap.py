from typing import Iterator, TypeVar
from collections.abc import MutableMapping, Mapping

_KT = TypeVar("_KT")
_MT = TypeVar("_MT")
_VT = TypeVar("_VT")


class ComposeMap(Mapping[_KT, _VT]):
    def __init__(self, dict_1: Mapping[_KT, _MT], dict_2: Mapping[_MT, _VT]):
        super().__init__()
        self.dict_1 = dict_1
        self.dict_2 = dict_2

    def __getitem__(self, __key: _KT) -> _VT:
        return self.dict_2[self.dict_1[__key]]
    
    def __iter__(self) -> Iterator[_KT]:
        return self.dict_1.__iter__()

    def __len__(self) -> int:
        return self.dict_1.__len__()