from playwright.sync_api import Page, Locator
from utils.page import locate

from typing import Literal, overload


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
        nth: int | Literal["random"] = 0,
        locate_options: dict = dict(),
        tap_options: dict = dict(),
    ):
    ...

@overload
def safe_tap(
        page: Page,
        selector: str,
        nth: int | Literal["random"] = 0,
        locate_options: dict = dict(),
        tap_options: dict = dict(),
    ):
    ...

def safe_tap(
        page: Page | Locator,
        selector: str = str(),
        nth: int | Literal["random"] = 0,
        locate_options: dict = dict(),
        tap_options: dict = dict(),
    ):
    element = locate(page, selector, nth, **locate_options) if selector else page
    if element is not None:
        scroll_into_view(element)
        element.tap(**tap_options)


def scroll_into_view(element: Locator):
    element.evaluate(JS["scrollIntoView()"])
