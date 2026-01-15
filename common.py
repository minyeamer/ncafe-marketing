from playwright.sync_api import Page

from typing import TypeVar
import random
import time

Delay = TypeVar("Delay", float, tuple)
Steps = TypeVar("Steps", int, tuple)


def main_url(mobile: bool) -> str:
    return f"https://{'m.' if mobile else 'www.'}naver.com"


def cafe_url(mobile: bool) -> str:
    if mobile:
        return "https://m.cafe.naver.com/"
    else:
        return "https://section.cafe.naver.com/ca-fe/home"


def goto_naver_main(
        page: Page,
        mobile: bool = True,
        goto_delay: Delay = (0.8, 2.2),
    ):
    if page.url != main_url(mobile):
        page.goto(main_url(mobile)), wait(goto_delay)


def goto_cafe_home(
        page: Page,
        mobile: bool = True,
        action_delay: Delay = (0.3, 0.6),
        goto_delay: Delay = (0.8, 2.2),
    ):
    if page.url == cafe_url(mobile):
        return
    goto_naver_main(page, mobile, goto_delay)

    if mobile:
        page.tap('#MM_logo [href="/aside/"]'), wait(goto_delay)
        if page.locator(".layer_alert").count() > 0:
            page.tap(".layer_alert .la_option"), wait(action_delay)
        page.tap('[href="https://m.cafe.naver.com"]'), wait(goto_delay)
    else:
        page.goto(cafe_url(mobile=False)), wait(goto_delay)
        # :has(a[href="https://cafe.naver.com"][target="_blank"])
        # from ncafe.utils.desktop import click_new_page
        # click_new_page(context, page, '[href="https://cafe.naver.com"]', steps=steps)


def wait(delay: float | tuple[float, float] | None = None):
    if delay is None:
        return
    elif isinstance(delay, tuple) and (len(delay) == 2):
        timeout = random.uniform(*delay)
    elif isinstance(delay, (float,int)):
        timeout = delay
    else:
        return
    time.sleep(timeout)
