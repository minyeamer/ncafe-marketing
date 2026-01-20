from __future__ import annotations

from playwright.sync_api import Page
from utils.common import wait, Delay


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
        goto_delay: Delay = (1, 3),
    ):
    if page.url != main_url(mobile):
        page.goto(main_url(mobile)), wait(goto_delay)


def goto_cafe_home(
        page: Page,
        mobile: bool = True,
        action_delay: Delay = (0.3, 0.6),
        goto_delay: Delay = (1, 3),
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
        # click_new_page(context, page, '[href="https://cafe.naver.com"]')
