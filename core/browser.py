from __future__ import annotations
import functools

from playwright.sync_api import sync_playwright, Playwright
from playwright.sync_api import Browser, BrowserContext, Page

from utils.common import AttrDict, Delay

from typing import TYPE_CHECKING
import os

if TYPE_CHECKING:
    from pathlib import Path

MOBILE_DEVICE = "Galaxy S24"


class BrowserDelay(AttrDict):

    def __init__(
            self,
            action: Delay = (0.3, 0.6),
            goto: Delay = (1, 3),
            reload: Delay = (3, 5),
            upload: Delay = (2, 4),
        ):
        super().__init__()
        self.action = action
        self.goto = goto
        self.reload = reload
        self.upload = upload

    def get_delays(self, keys: list[str]) -> dict[str,Delay]:
        return {f"{key}_delay": getattr(self, key) for key in keys}


class BrowserState(AttrDict):

    def __init__(self):
        super().__init__()
        self.__playwright: Playwright = None
        self.__browser: Browser = None
        self.__context: BrowserContext = None
        self.__page: Page = None

    @property
    def playwright(self) -> Playwright:
        return self.__playwright

    @property
    def browser(self) -> Browser:
        return self.__browser

    @property
    def context(self) -> BrowserContext:
        return self.__context

    @property
    def page(self) -> Page:
        return self.__page

    def set_playwright(self, playwright: Playwright):
        self.__playwright = playwright

    def launch_browser(self, **kwargs):
        self.__browser = self.__playwright.chromium.launch(**kwargs)

    def close_browser(self):
        self.__browser.close()

    def new_context(self, device: str = str(), state: str | Path | None = None, **kwargs):
        if device:
            kwargs.update(self.__playwright.devices[device])
        if state and os.path.exists(str(state)):
            kwargs.update(storage_state=state)
        self.__context = self.__browser.new_context(**kwargs)

    def new_page(self):
        self.__page = self.__context.new_page()


class BrowserController(AttrDict):

    def __init__(
            self,
            device: str = str(),
            mobile: bool = True,
            headless: bool = True,
            action_delay: Delay = (0.3, 0.6),
            goto_delay: Delay = (1, 3),
            reload_delay: Delay = (3, 5),
            upload_delay: Delay = (2, 4),
        ):
        super().__init__()
        self.device: str = device
        self.mobile: bool = mobile
        self.headless: bool = headless
        self.delays: BrowserDelay = BrowserDelay(action_delay, goto_delay, reload_delay, upload_delay)
        self.states: BrowserState = BrowserState()

    @property
    def playwright(self) -> Playwright:
        return self.states.playwright

    @property
    def browser(self) -> Browser:
        return self.states.browser

    @property
    def context(self) -> BrowserContext:
        return self.states.context

    @property
    def page(self) -> Page:
        return self.states.page

    def reset_states(self):
        del self.states
        self.states = BrowserState()

    def with_browser(func):
        @functools.wraps(func)
        def wrapper(self: BrowserController, *args, state: str | Path | None = None, **kwargs):
            self.reset_states()
            try:
                with sync_playwright() as playwright:
                    self.states.set_playwright(playwright)
                    self.states.launch_browser(headless=self.headless)
                    try:
                        self.states.new_context(self.device, state)
                        self.states.new_page()
                        return func(self, *args, state=state, **kwargs)
                    finally:
                        if state and self.context:
                            self.context.storage_state(path=str(state))
                        self.states.close_browser()
            finally:
                self.reset_states()
        return wrapper
