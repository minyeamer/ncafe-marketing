from __future__ import annotations

from playwright.sync_api import Page, Locator

from typing import Literal, TypeVar, TypedDict, overload, TYPE_CHECKING
from numbers import Real
import random

if TYPE_CHECKING:
    from typing import Pattern

MinX = TypeVar("MinX", bound=Real)
MinY = TypeVar("MinY", bound=Real)
MaxX = TypeVar("MaxX", bound=Real)
MaxY = TypeVar("MaxY", bound=Real)

class Overlay(TypedDict, total=False):
    top: Real | None
    right: Real | None
    bottom: Real | None
    left: Real | None

class LocatorFilters(TypedDict, total=False):
    has_text: Pattern[str] | str | None
    has_not_text: Pattern[str] | str | None
    has: Locator | None
    has_not: Locator | None
    boundary: Locator | None
    overlay: Overlay | None
    threshold: float

class Offset(TypedDict, total=False):
    x_offset: float | None
    y_offset: float | None

Position = Literal[
    "top_left", "top_center", "top_right",
    "center_left", "center", "center_right", 
    "bottom_left", "bottom_center", "bottom_right"
]

POSITION_MAP = {
    "top_left": (0.0, 0.0),
    "top_center": (0.5, 0.0),
    "top_right": (1.0, 0.0),
    "center_left": (0.0, 0.5),
    "center": (0.5, 0.5),
    "center_right": (1.0, 0.5),
    "bottom_left": (0.0, 1.0),
    "bottom_center": (0.5, 1.0),
    "bottom_right": (1.0, 1.0)
}


def locate(
        page: Page,
        selector: str,
        nth: int | Literal["random"] = 0,
        *,
        has_text: Pattern[str] | str | None = None,
        has_not_text: Pattern[str] | str | None = None,
        has: Locator | None = None,
        has_not: Locator | None = None,
        boundary: Locator | None = None,
        overlay: Overlay | None = None,
        threshold: float = 0.5,
    ) -> Locator:
    kwargs = dict(has_text=has_text, has_not_text=has_not_text, has=has, has_not=has_not)
    locator = page.locator(selector, **kwargs)
    if (element := locator.first):
        if boundary is not None:
            _, min_y, _, max_y = range_boundaries(page, boundary, overlay)
            visible = [element for element in locator.all() if is_visible(element, min_y, max_y, threshold)]
            return random.choice(visible) if nth == "random" else visible[nth]
        elif isinstance(nth, int):
            return locator.all()[nth] if nth > 0 else element
        elif nth == "random":
            return random.choice(locator.all())
        else:
            raise TypeError("list indices must be integers or slices, not str")


def locate_all(
        page: Page,
        selector: str,
        *,
        has_text: Pattern[str] | str | None = None,
        has_not_text: Pattern[str] | str | None = None,
        has: Locator | None = None,
        has_not: Locator | None = None,
        boundary: Locator | None = None,
        overlay: Overlay | None = None,
        threshold: float = 0.5,
    ) -> list[Locator]:
    kwargs = dict(has_text=has_text, has_not_text=has_not_text, has=has, has_not=has_not)
    locator = page.locator(selector, **kwargs)
    if locator.first:
        if boundary is not None:
            _, min_y, _, max_y = range_boundaries(page, boundary, overlay)
            return [element for element in locator.all() if is_visible(element, min_y, max_y, threshold)]
        else:
            return locator.all()
    else:
        return list()


def is_visible(
        element: Locator,
        min_y: Real,
        max_y: Real,
        threshold: float = 0.5,
    ) -> bool:
    el_box = element.bounding_box()
    if not el_box:
        return False

    y, height = el_box['y'], el_box["height"]
    if (y <= min_y) and (max_y <= (y + height)):
        return True

    threshold = min(max(threshold, 0.), 1.)
    min_el_y = y + (height * (1. - threshold))
    max_el_y = y + (height * threshold)
    return (height > 0) and (min_y <= min_el_y) and (max_el_y <= max_y)


def get_relative_position(
        element: Locator,
        min_y: Real,
        max_y: Real,
        threshold: float = 0.5,
    ) -> Literal["above","within","below","hidden"]:
    el_box = element.bounding_box()
    y, height = el_box['y'], el_box["height"]
    threshold = min(max(threshold, 0.), 1.)

    if height <= 0:
        return "hidden"
    elif (y <= min_y) and (max_y <= (y + height)):
        return "within"
    elif min_y > (y + (height * (1. - threshold))):
        return "above"
    elif max_y < (y + (height * threshold)):
        return "below"
    else:
        return "within"


def range_boundaries(
        page: Page,
        boundary: Locator | None = None,
        overlay: Overlay | None = None,
    ) -> tuple[MinX, MinY, MaxX, MaxY]:
    viewport = page.viewport_size
    width, height = viewport["width"], viewport["height"]

    if boundary is not None:
        box = boundary.bounding_box()
        min_x, max_x = max(0, box['x']), min(width, box['x'] + box["width"])
        min_y, max_y = max(0, box['y']), min(height, box['y'] + box["height"])
    else:
        min_x, min_y, max_x, max_y = 0, 0, width, height

    if overlay:
        if "top" in overlay: min_y = max(min_y, overlay["top"])
        if "right" in overlay: min_x = max(min_x, overlay["right"])
        if "bottom" in overlay: max_y = min(max_y, overlay["bottom"])
        if "left" in overlay: max_x = min(max_x, overlay["left"])
    return min_x, min_y, max_x, max_y


@overload
def pos(
        element: Locator,
        *,
        position: Literal[
            "top_left", "top_center", "top_right",
            "center_left", "center", "center_right", 
            "bottom_left", "bottom_center", "bottom_right"
        ] | None = None,
        x_offset: float | None = None,
        y_offset: float | None = None,
    ) -> tuple[float, float] | tuple[None, None]:
    ...

@overload
def pos(
        page: Page,
        selector: str | None = None,
        nth: int | Literal["random"] = 0,
        filters: LocatorFilters = dict(),
        position: Literal[
            "top_left", "top_center", "top_right",
            "center_left", "center", "center_right", 
            "bottom_left", "bottom_center", "bottom_right"
        ] | None = None,
        x_offset: float | None = None,
        y_offset: float | None = None,
    ) -> tuple[float, float] | tuple[None, None]:
    ...

def pos(
        page: Page | Locator,
        selector: str | None = None,
        nth: int | Literal["random"] = 0,
        filters: LocatorFilters = dict(),
        position: Literal[
            "top_left", "top_center", "top_right",
            "center_left", "center", "center_right", 
            "bottom_left", "bottom_center", "bottom_right"
        ] | None = None,
        x_offset: float | None = None,
        y_offset: float | None = None,
    ) -> tuple[float, float] | tuple[None, None]:
    if not (isinstance(x_offset, float) and isinstance(y_offset, float)):
        x_offset, y_offset = POSITION_MAP.get(position) or (0.5, 0.5)

    element = locate(page, selector, nth, **filters) if selector else page
    if element is not None:
        box = element.bounding_box()
        x = box['x'] + box["width"] * x_offset
        y = box['y'] + box["height"] * y_offset
        return x, y
    else:
        return None, None
