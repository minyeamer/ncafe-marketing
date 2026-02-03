from __future__ import annotations

import time

from typing import TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, Hashable
    _KT = TypeVar("_KT", Hashable)
    _VT = TypeVar("_VT", Any)


class ActionTimer(dict):

    def start_timer(self, key: _KT):
        self.update({key: time.perf_counter()})

    def end_timer(self, key: _KT, ndigits: int | None = None) -> float | None:
        try:
            return self.get_elapsed_time(key, ndigits)
        finally:
            self.pop(key, None)

    def get_elapsed_time(self, key: _KT, ndigits: int | None = None) -> float | None:
        if key in self:
            elapsed_time = time.perf_counter() - self[key]
            return round(elapsed_time, ndigits) if isinstance(ndigits, int) else elapsed_time
        else:
            return None

    def get_all_elapsed_times(self, ndigits: int | None = None) -> dict[_KT, float]:
        round_n = (lambda x: round(x, ndigits)) if isinstance(ndigits, int) else (lambda x: x)
        return {key: round_n(time.perf_counter() - start_time) for key, start_time in self.items()}

    def gte(self, key: _KT, value: float) -> bool:
        if (key in self) and isinstance(value, (float,int)):
            return (time.perf_counter() - self[key]) >= value
        else:
            return True
