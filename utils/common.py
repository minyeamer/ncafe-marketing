from __future__ import annotations

from playwright.sync_api import Locator #, Page

from typing import TypeVar
import json
import random
import time

Delay = TypeVar("Delay", float, tuple)
Steps = TypeVar("Steps", int, tuple)


def print_json(data: dict | list, verbose: int = 0):
    if verbose > 0:
        print(json.dumps(data, indent=(2 if verbose > 1 else None), ensure_ascii=False, default=str))


def wait(delay: float | tuple[float, float] | None = None, ndigits: int | None = None):
    if delay is None:
        return
    elif isinstance(delay, tuple) and (len(delay) == 2):
        timeout = random.uniform(*delay)
        if isinstance(ndigits, int):
            timeout = round(timeout, ndigits)
    elif isinstance(delay, (float,int)):
        timeout = delay
    else:
        return
    time.sleep(timeout)


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
