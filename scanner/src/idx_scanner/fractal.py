# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Port of Fractal Channel / FracChan_v2 (Pine v1), © NielsG.
# Derived from user-supplied formula documented in SOT.md section 8.
# Python representation and explicit available_session: IDX Night Scanner.
# Transaction rules are project additions in strategies.py, not NielsG's script.

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from .models import Bar, digest


@dataclass(frozen=True)
class Level:
    id: str
    price: float
    pivot_date: date
    available_session: date


def levels(bars: Sequence[Bar]) -> tuple[tuple[Level | None, Level | None], ...]:
    ceiling = floor = None
    result = []
    for t, bar in enumerate(bars):
        if t >= 5:
            pivot = bars[t - 3]
            others = (bars[t - 5], bars[t - 4], bars[t - 2], bars[t - 1])
            if all(pivot.high >= other.high for other in others):
                ceiling = Level(
                    digest(("upper", pivot.session, bar.session)),
                    pivot.high,
                    pivot.session,
                    bar.session,
                )
            if all(pivot.low <= other.low for other in others):
                floor = Level(
                    digest(("lower", pivot.session, bar.session)),
                    pivot.low,
                    pivot.session,
                    bar.session,
                )
        result.append((ceiling, floor))
    return tuple(result)
