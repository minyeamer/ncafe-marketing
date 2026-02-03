from __future__ import annotations

from playwright.sync_api import Locator #, Page

from typing import TypeVar, TYPE_CHECKING
from pathlib import Path
import json
import random
import time

if TYPE_CHECKING:
    from typing import Any, Callable, Hashable
    _KT = TypeVar("_KT", Hashable)
    _VT = TypeVar("_VT", Any)

Delay = TypeVar("Delay", float, tuple)
Steps = TypeVar("Steps", int, tuple)

DictRecursive = TypeVar("DictRecursive", bound=dict)


class AttrDict(dict):

    def __setattr__(self, name: str, value: _VT):
        super().__setattr__(name, value)
        if name.startswith('_'):
            class_name, attr_name = name.split("__", 1)
            self[class_name] = dict(self.get(class_name) or dict(), **{attr_name: value})
        else:
            super().__setitem__(name, value)

    def __delattr__(self, name: str):
        super().__delattr__(name)
        if name.startswith('_'):
            class_name, attr_name = name.split("__", 1)
            (self.get(class_name) or dict()).pop(attr_name, None)
        else:
            super().__delitem__(name)

    def __setitem__(self, key: _KT, value: _VT):
        super().__setitem__(key, value)
        if isinstance(key, str):
            super().__setattr__(key, value)

    def __delitem__(self, key: _KT):
        super().__delattr__(key)
        if isinstance(key, str):
            super().__delitem__(key)

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        for key, value in dict(*args, **kwargs).items():
            if isinstance(key, str):
                setattr(self, key, value)

    def dumps(
            self,
            ensure_ascii: bool = False,
            indent: int | str | None = 2,
            default: Callable = str,
            **kwargs
        ) -> str:
        return json.dumps(self, ensure_ascii=ensure_ascii, indent=indent, default=default, **kwargs)


def print_json(data: dict | list, verbose: int | str | Path = 0):
    if isinstance(verbose, int):
        if verbose > 0:
            print(json.dumps(data, indent=(2 if verbose > 1 else None), ensure_ascii=False, default=str))
    elif verbose:
        with open(str(verbose), 'a', encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False, default=str)
            file.write('\n')


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
