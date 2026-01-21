from __future__ import annotations

from playwright.sync_api import Page, Locator
from core.agent import ArticleParams, ArticleContext
from core.agent import select_articles, ChatModel, Prompts

from utils.common import wait, Delay
from utils.locator import Overlay, locate_all
from utils.locator import is_visible, range_boundaries
from utils.mouse import safe_wheel
from utils.touchscreen import safe_tap

from typing import TypeVar, TypedDict, TYPE_CHECKING
from urllib.parse import urlparse
import random
import re

if TYPE_CHECKING:
    from typing import Iterable, Set
    from pathlib import Path

MenuName = TypeVar("MenuName", bound=str)
ArticleId = TypeVar("ArticleId", bound=str)

class CafeRanges(TypedDict):
    boundary: Locator
    overlay: Overlay


###################################################################
###################### Action 1: :goto_cafe: ######################
###################################################################

def goto_cafe(
        page: Page,
        cafe_name: str,
        goto_delay: Delay = (1, 3),
    ):
    page.tap(f'.mycafe_flicking:not([style="display: none;"]) a:has-text("{cafe_name}")')
    wait(goto_delay)


def get_cafe_ranges(page: Page, header: bool = True, tab: bool = False) -> CafeRanges:
    return dict(
        boundary = page.locator("body").first,
        overlay = _get_cafe_overlay(page, header, tab),
    )


def _get_cafe_overlay(page: Page, header: bool = True, tab: bool = False) -> Overlay:
    header_height = page.locator(".WebHeader").bounding_box()["height"] if header else 0
    tab_height = page.locator(".ArticleTab").bounding_box()["height"] if tab else 0
    return dict(top = (header_height + tab_height))


###################################################################
###################### Action 2: :goto_menu: ######################
###################################################################

def goto_menu(
        page: Page,
        menu_name: str = str(),
        action_delay: Delay = (0.3, 0.6),
        goto_delay: Delay = (1, 3),
        has_text: Iterable[str] = list(),
        has_not_text: Iterable[str] = list(),
    ) -> MenuName:
    page.tap(f'header button:has-text("메뉴")'), wait(action_delay)
    if menu_name:
        safe_tap(page, f'a:has-text("{menu_name}")'), wait(goto_delay)
        return menu_name
    else:
        has_text = re.compile('|'.join(has_text)) if has_text else None
        has_not_text = re.compile('|'.join(has_not_text)) if has_not_text else None
        a = safe_tap(page, "a.link_menu", nth="random", filters=dict(has_text=has_text, has_not_text=has_not_text))
        return a.locator(".menu").text_content()


def _get_menu_boundary(page: Page) -> Locator:
    return page.locator(".list_section").first


def _get_menu_overlay(page: Page) -> Overlay:
    return dict(top = page.locator(".header_top").first.bounding_box()["height"])


###################################################################
################### Action 3: :explore_articles: ##################
###################################################################

def explore_articles(
        page: Page,
        cafe_name: str,
        menu_name: str,
        visited: Set[ArticleId] = set(),
        model: ChatModel | None = None,
        prompts: str | Path | Prompts | None = None,
        temperature: float | None = 0.1,
        **kwargs
    ) -> list[ArticleContext]:
    articles = list_articles(page, visited)
    if articles:
        return select_articles(articles, cafe_name, menu_name, model, prompts, temperature, **kwargs)
    else:
        return list()


def list_articles(page: Page, visited: Set[ArticleId] = set()) -> list[ArticleParams]:
    articles = list()
    for article in locate_all(page, ".mainLink", **get_cafe_ranges(page, header=True, tab=True)):
        params = _parse_params(article.get_attribute("href") or str())
        if params["articleid"] not in visited:
            visited.add(params["articleid"])
            params["title"] = article.locator(".tit").first.text_content().strip()
            articles.append(params)
    return articles


def _parse_params(href: str) -> dict[str,str]:
    query = urlparse(href).query
    return dict([kv.split('=') for kv in query.split('&')])

################### Action 9: :navigate_article: ##################

def next_articles(page: Page, action_delay: Delay = (0.3, 0.6)):
    ranges = get_cafe_ranges(page, header=True, tab=True)
    delta = page.viewport_size["height"] - ranges["overlay"]["top"]
    safe_wheel(page, delta=delta, **ranges)
    wait(action_delay)


def reload_articles(page: Page, goto_delay: Delay = (1, 3)):
    page.reload(), wait(goto_delay)


###################################################################
##################### Action 4: :goto_article: ####################
###################################################################

def goto_article(page: Page, article_id: str, goto_delay: Delay = (1, 3)) -> bool:
    for article in locate_all(page, ".mainLink", **get_cafe_ranges(page, header=True, tab=True)):
        params = _parse_params(article.get_attribute("href") or str())
        if article_id == params["articleid"]:
            article.tap(), wait(goto_delay)
            return True
    return False


###################################################################
##################### Action 5: :read_article: ####################
###################################################################

def read_article(page: Page, wait_until_read: bool = True) -> list[str]:
    lines, visible_lines = list(), list()
    _, min_y, _, max_y = range_boundaries(page, **get_cafe_ranges(page, header=True, tab=False))

    selector = lambda tag: f'#postContent {tag}:not([style="display: none;"]):not(.se-module-oglink *)'
    for el in locate_all(page, ", ".join([selector('p'), selector("img")])):
        tag_name = el.evaluate("el => el.tagName")
        if tag_name == "img":
            line = f"![{el.get_attribute('alt') or '이미지'}]({el.get_attribute('src')})"
        else:
            line = el.text_content().replace('\u200b', '').strip()
        lines.append(line)
        if is_visible(el, min_y, max_y):
            visible_lines.append(line)

    seconds = round(_estimate_reading_seconds(visible_lines), 1)
    if wait_until_read:
        wait(seconds)
    else:
        print(f"{seconds}초 대기")

    return lines


def _estimate_reading_seconds(lines: Iterable[str], kor_cpm: int = 160, eng_cpm: int = 238) -> float:
    seconds = 0.
    for line in lines:
        if not line:
            continue
        elif line.startswith("![") and line.endswith(')'):
            seconds += 3.
        elif (cpm := _calc_weighted_cpm(line, kor_cpm, eng_cpm)):
            total_chars = _count_hangul_chars(line) + _count_english_chars(line)
            seconds += round((total_chars / cpm) * 60, 5)
    return seconds


def _calc_weighted_cpm(text: str, kor_cpm: int = 160, eng_cpm: int = 238) -> float:
    kor_chars = _count_hangul_chars(text)
    eng_chars = _count_english_chars(text)
    total_chars = kor_chars + eng_chars
    if total_chars == 0:
        return 0
    return (kor_chars * kor_cpm + eng_chars * eng_cpm) / total_chars * 3


def _count_hangul_chars(text) -> int:
    return len(re.sub(r"[^ㄱ-ㅎㅏ-ㅣ가-힣]", '', text))


def _count_english_chars(text) -> int:
    return len(re.sub(r"[^a-zA-Z0-9]", '', text))

##################### Action 8: :like_article: ####################

def like_article(page: Page):
    like_button = page.locator('.right_area [data-type="like"]').first
    if like_button.get_attribute("aria-pressed") == "false":
        like_button.tap()

################### Action 9: :navigate_article: ##################

def next_lines(page: Page, action_delay: Delay = (0.3, 0.6)):
    ranges = get_cafe_ranges(page, header=True, tab=False)
    delta = page.viewport_size["height"] - ranges["overlay"]["top"]
    safe_wheel(page, delta=delta, **ranges)
    wait(action_delay)


def prev_lines(page: Page, action_delay: Delay = (0.3, 0.6)):
    ranges = get_cafe_ranges(page, header=True, tab=False)
    delta = page.viewport_size["height"] - ranges["overlay"]["top"]
    safe_wheel(page, delta=(delta * -1), **ranges)
    wait(action_delay)


def go_back(page: Page, goto_delay: Delay = (1, 3)):
    page.go_back(), wait(goto_delay)


###################################################################
#################### Action 6: :write_comment: ####################
###################################################################

def write_comment(page: Page, comment: str, action_delay: Delay = (0.3, 0.6), goto_delay: Delay = (1, 3)):
    page.locator(".right_area .f_reply").tap(), wait(action_delay)
    page.locator(".textarea_write").tap(), wait(action_delay)
    page.locator(".text_input_area").type(comment, delay=100), wait(action_delay)
    go_back(page, goto_delay)


###################################################################
#################### Action 7: :write_article: ####################
###################################################################

def write_article(page: Page):
    ...
