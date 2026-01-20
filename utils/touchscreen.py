from __future__ import annotations

from playwright.sync_api import Page, Locator
from utils.locator import LocatorFilters, locate
from utils.locator import Position, Offset, pos
from utils.mouse import Overlay, safe_wheel

from typing import overload, TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Literal


JS = {
    "scrollIntoView()": 
"""(el) => {
    el.scrollIntoView({
        block: 'center',
        behavior: 'smooth'
    });
}""",
}


@overload
def safe_tap(
        element: Page,
        *,
        position: Position | Offset | None = None,
        boundary: Locator | Literal["viewport"] | None = None,
        overlay: Overlay | None = None,
        **kwargs
    ) -> Locator | None:
    ...

@overload
def safe_tap(
        page: Page,
        selector: str,
        nth: int | Literal["random"] = 0,
        filters: LocatorFilters = dict(),
        position: Position | Offset | None = None,
        boundary: Locator | Literal["viewport"] | None = None,
        overlay: Overlay | None = None,
        **kwargs
    ) -> Locator | None:
    ...

def safe_tap(
        page: Page | Locator,
        selector: str | None = None,
        nth: int | Literal["random"] = 0,
        filters: LocatorFilters = dict(),
        position: Position | Offset | None = None,
        boundary: Locator | Literal["viewport"] | None = None,
        overlay: Overlay | None = None,
        threshold: float = 0.5,
        **kwargs
    ) -> Locator | None:
    element = locate(page, selector, nth, **filters) if selector else page
    if element is not None:
        if selector and (boundary is not None):
            boundary = boundary if isinstance(boundary, Locator) else None
            safe_wheel(page, element, boundary, overlay, threshold)
        else:
            element.evaluate(JS["scrollIntoView()"])

        position = dict(position=position) if isinstance(position, str) else position
        x, y = pos(element, **position) if isinstance(position, dict) else None, None
        if (x is not None) and (y is not None):
            element.touchscreen.tap(x, y)
        else:
            element.tap(**kwargs)
        return element
