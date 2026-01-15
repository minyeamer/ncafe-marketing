from playwright.sync_api import Page
from common import wait, Delay
from utils.page import locate, locate_where
from utils.mobile import safe_tap

from typing import Sequence


def goto_cafe(
        page: Page,
        cafe_name: str,
        goto_delay: Delay = (0.8, 2.2),
    ):
    page.tap(f'.mycafe_flicking:not([style="display: none;"]) a:has-text("{cafe_name}")')
    wait(goto_delay)


def goto_menu(
        page: Page,
        menu_name: str = str(),
        action_delay: Delay = (0.3, 0.6),
        goto_delay: Delay = (0.8, 2.2),
        excludes: Sequence[str] = list(),
    ) -> str | None:
    page.tap(f'header button:has-text("메뉴")'), wait(action_delay)
    if menu_name:
        safe_tap(page, f'a:has-text("{menu_name}")'), wait(goto_delay)
        return menu_name
    else:
        if excludes:
            a = locate_where(page, "a.link_menu", excludes=excludes, offset="random")
        else:
            a = locate(page, "a.link_menu", nth="random")
        menu_name = a.text_content()
        safe_tap(a), wait(goto_delay)
        return menu_name


def goto_article(page: Page):
    ...


def read_article(page: Page):
    ...


def write_article(page: Page):
    ...


def write_comment(page: Page):
    ...


def scroll_down(page: Page):
    ...


def scroll_up(page: Page):
    ...


def like_article(page: Page):
    ...


def go_back(page: Page):
    page.go_back()


def refresh(page: Page):
    page.reload()
