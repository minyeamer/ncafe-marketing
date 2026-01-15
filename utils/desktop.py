from playwright.sync_api import BrowserContext, Page
from utils.page import locate
from typing import Literal, TypeVar
import random

Steps = TypeVar("Steps", int, tuple)


LAST: int = -1

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


def safe_click(
        page: Page,
        selector: str,
        nth: int | Literal["random"] = 0,
        method: Literal["locator","mouse"] = "locator",
        position: Literal[
            "top_left", "top_center", "top_right",
            "center_left", "center", "center_right", 
            "bottom_left", "bottom_center", "bottom_right"
        ] | None = None,
        x_offset: float | None = None,
        y_offset: float | None = None,
        steps: int | tuple[int, int] | None = None, # 1
        locate_options: dict = dict(),
        click_options: dict = dict(),
    ):
    if not (isinstance(x_offset, float) and isinstance(y_offset, float)):
        offset = POSITION_MAP.get(position or "center")
        if not offset:
            return
        x_offset, y_offset = offset

    if isinstance(steps, tuple) and (len(steps) == 2):
        steps = random.randint(*steps)
    elif not isinstance(steps, int):
        steps = None

    if (element := locate(page, selector, nth, **locate_options)) is not None:
        box = element.bounding_box()
        x, y = box['x'] + box['width'] * x_offset, box['y'] + box['height'] * y_offset

        page.mouse.move(x, y, steps=steps)
        if method == "locator":
            element.click(**click_options)
        elif click_options:
            page.mouse.click(x, y, **click_options)
        else:
            page.mouse.down()
            page.mouse.up()


def click_new_page(
        context: BrowserContext,
        page: Page,
        selector: str,
        nth: int | Literal["random"] = 0,
        steps: int | tuple[int, int] | None = None, # 1
        page_timeout: float | None = None, # 30000
        wait_for: Literal['domcontentloaded', 'load', 'networkidle'] | None = None, # load
        locate_options: dict = dict(),
        click_options: dict = dict(),
    ):
    with context.expect_page(timeout=page_timeout) as new_page_info:
        options = dict(locate_options=locate_options, click_options=click_options)
        safe_click(page, selector, nth, method="locator", steps=steps, **options)
    new_page = new_page_info.value
    new_page.wait_for_load_state(wait_for)
    context.pages[LAST].bring_to_front()


# def click_mouse(
#         page: Page,
#         selector: str,
#         algorithm: Literal["perlin","bezier","gaussian"] = "bezier",
#         interval: float = 0.01,
#         locate_options: dict = dict(),
#     ):
#     from oxymouse import OxyMouse
#     import pyautogui

#     if interval:
#         pyautogui.PAUSE = interval
#     from_x, from_y = pyautogui.position()
#     elem = page.locator(selector, **locate_options).first
#     if (box := elem.bounding_box()):
#         to_x, to_y = int(box['x'] + box['width'] * 0.5), int(box['y'] + box['height'] * 0.5)
#     else:
#         return

#     mouse = OxyMouse(algorithm=algorithm)
#     for nx, ny in mouse.generate_coordinates(from_x=from_x, from_y=from_y, to_x=to_x, to_y=to_y):
#         pyautogui.moveTo(nx, ny)
#     pyautogui.click()
