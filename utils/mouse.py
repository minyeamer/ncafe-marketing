from __future__ import annotations

from playwright.sync_api import BrowserContext, Page, Locator
from utils.common import wait
from utils.locator import LocatorFilters, locate
from utils.locator import Position, Offset, pos
from utils.locator import Overlay, is_visible, get_relative_position, range_boundaries

from typing import overload, TYPE_CHECKING
import random

if TYPE_CHECKING:
    from typing import Literal


@overload
def safe_click(
        element: Locator,
        *,
        on: Literal["locator","mouse"] = "locator",
        position: Position | Offset | None = None,
        steps: int | tuple[int, int] | None = None,
        **kwargs
    ) -> Locator | None:
    ...

@overload
def safe_click(
        page: Page,
        selector: str,
        nth: int | Literal["random"] = 0,
        on: Literal["locator","mouse"] = "locator",
        filters: LocatorFilters = dict(),
        position: Position | Offset | None = None,
        steps: int | tuple[int, int] | None = None,
        **kwargs
    ) -> Locator | None:
    ...

def safe_click(
        page: Page | Locator,
        selector: str | None = None,
        nth: int | Literal["random"] = 0,
        filters: LocatorFilters = dict(),
        position: Position | Offset | None = None,
        steps: int | tuple[int, int] | None = None,
        **kwargs
    ) -> Locator | None:
    element = locate(page, selector, nth, **filters) if selector else page
    if element is not None:
        position = dict(position=position) if isinstance(position, str) else position
        x, y = pos(element, **position) if isinstance(position, dict) else None, None

        if (x is not None) and (y is not None):
            if isinstance(steps, tuple) and (len(steps) == 2):
                steps = random.randint(*steps)
            elif not isinstance(steps, int):
                steps = None

            page.mouse.move(x, y, steps=steps)
            if kwargs:
                page.mouse.click(x, y, **kwargs)
            else:
                page.mouse.down()
                page.mouse.up()
        else:
            element.click(**kwargs)
        return element


def click_new_page(
        context: BrowserContext,
        page: Page,
        selector: str,
        nth: int | Literal["random"] = 0,
        steps: int | tuple[int, int] | None = None, # 1
        page_timeout: float | None = None, # 30000
        wait_for: Literal["domcontentloaded", "load", "networkidle"] | None = None, # load
        locate_options: dict = dict(),
        click_options: dict = dict(),
    ):
    with context.expect_page(timeout=page_timeout) as new_page_info:
        options = dict(locate_options=locate_options, click_options=click_options)
        safe_click(page, selector, nth, steps=steps, **options)
    new_page = new_page_info.value
    new_page.wait_for_load_state(wait_for)
    context.pages[-1].bring_to_front()


def safe_wheel(
        page: Page,
        target: Locator | None = None,
        boundary: Locator | None = None,
        overlay: Overlay | None = None,
        threshold: float = 0.5,
        delta: float | None = None,
    ):
    if target is not None:
        _safe_wheel_to_target(page, target, boundary, overlay, threshold)
    elif isinstance(delta, (float,int)) and (delta != 0):
        min_x, min_y, max_x, max_y = range_boundaries(page, boundary, overlay)
        page.mouse.move((min_x + max_x) // 2, (min_y + max_y) // 2, steps=int(random.uniform(5, 10)))
        _safe_wheel_by_delta(page, delta)
    else:
        return


def _safe_wheel_to_target(
        page: Page,
        target: Locator,
        boundary: Locator | None = None,
        overlay: Overlay | None = None,
        threshold: float = 0.5,
    ):
    min_x, min_y, max_x, max_y = range_boundaries(page, boundary, overlay)

    where = get_relative_position(target, min_y, max_y, threshold)
    direction = {"above": -1, "below": 1}.get(where)
    if direction is None:
        return

    prev_y, accel = target.bounding_box()['y'], 1.
    page.mouse.move((min_x + max_x) // 2, (min_y + max_y) // 2, steps=int(random.uniform(5, 10)))

    while True:
        if is_visible(target, min_y, max_y, threshold):
            break

        dy = round(random.uniform(11 * direction, 22 * direction) * accel, 1)
        page.mouse.wheel(0, dy)
        wait((0.001, 0.01))
        accel = min(accel + 0.1, 3.)

        if target.bounding_box()['y'] == prev_y:
            wait(0.01)
        if (cur_y := target.bounding_box()['y']) == prev_y:
            break
        else:
            prev_y = cur_y


def _safe_wheel_by_delta(page: Page, delta: float):
    dist, accel = 0., 1.
    direction = -1 if delta < 0. else 1

    while abs(dist) < abs(delta):

        dy = round(random.uniform(11 * direction, 22 * direction) * accel, 1)
        if abs(dist + dy) > abs(delta):
            page.mouse.wheel(0, abs(delta - dist) * direction)
            break
        else:
            page.mouse.wheel(0, dy)
            dist += dy
        wait((0.001, 0.01))
        accel = min(accel + 0.1, 3.)
