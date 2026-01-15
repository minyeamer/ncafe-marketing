from playwright.sync_api import Page, Locator

from typing import Iterable, Literal
import random
import re


def locate(page: Page, selector: str, nth: int | Literal["random"] = 0, **options) -> Locator:
    locator = page.locator(selector, **options)
    if (element := locator.first):
        if isinstance(nth, int):
            return locator.all()[nth] if nth > 0 else element
        elif nth == "random":
            return random.choice(locator.all())
        else:
            raise TypeError("list indices must be integers or slices, not str")


def locate_all(page: Page, selector: str, **options) -> list[Locator]:
    locator = page.locator(selector, **options)
    return locator.all() if locator.first else list()


def locate_where(
        page: Page,
        selector: str,
        includes: Iterable[str] = list(),
        excludes: Iterable[str] = list(),
        offset: int | Literal["all","random"] = 0,
        **options
    ) -> Locator | list[Locator] | None:
    locators = list()
    for locator in locate_all(page, selector, **options):
        text = locator.text_content()
        if (not includes) or re.search('|'.join(includes), text):
            if not (excludes and re.search('|'.join(excludes), text)):
                locators.append(locator)

    if isinstance(offset, int):
        return locators[offset] if locators else None
    elif offset == "all":
        return locators
    elif offset == "random":
        return random.choice(locators) if locators else None
    else:
        raise TypeError("list indices must be integers or slices, not str")


def remove_attribute(element: Locator, attribute: str, exact: str | None = None):
    element.evaluate("el => { if (el.getAttribute('$attribute')$condition) el.removeAttribute('$attribute'); }"
        .replace("$attribute", attribute).replace("$condition", (f" === '{exact}'" if exact else '')))


# def copy_and_paste(page: Page, selector: str, text: str):
#     import platform
#     import pyperclip

#     page.click(selector)
#     pyperclip.copy(text)

#     key = "Meta+V" if platform.system() == "Darwin" else "Control+V"
#     page.keyboard.press(key)
