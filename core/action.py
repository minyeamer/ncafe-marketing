from __future__ import annotations

from playwright.sync_api import Page, Locator

from core.agent import ChatModel, Prompt
from core.agent import ArticleParams, select_articles
from core.agent import ArticleData, create_comment

from utils.common import wait, Delay
from utils.locator import Overlay, locate_all
from utils.locator import is_visible, range_boundaries
from utils.mouse import safe_wheel
from utils.touchscreen import safe_tap

from typing import TypeVar, TypedDict, TYPE_CHECKING
from urllib.parse import urlparse
import datetime as dt
import random
import re
import time

if TYPE_CHECKING:
    from typing import Iterable, Literal, Set
    from pathlib import Path

MenuName = TypeVar("MenuName", bound=str)
ArticleId = TypeVar("ArticleId", bound=str)
Comment = TypeVar("Comment", bound=str)

class CafeRanges(TypedDict):
    boundary: Locator
    overlay: Overlay

class Contents(TypedDict):
    lines: list[str]
    visible_lines: list[str]
    total: int
    read_start: int
    read_end: int
    read_done: bool


###################################################################
###################### Action 1 - :goto_cafe: #####################
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
    header_height = page.locator(".WebHeader").first.bounding_box()["height"] if header else 0
    tab_height = page.locator(".ArticleTab").first.bounding_box()["height"] if tab else 0
    return dict(top = (header_height + tab_height))


###################################################################
###################### Action 2 - :goto_menu: #####################
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
        safe_tap(page, f'a:has-text("{menu_name}")', delay=action_delay), wait(goto_delay)
        return menu_name
    else:
        has_text = re.compile('|'.join(has_text)) if has_text else None
        has_not_text = re.compile('|'.join(has_not_text)) if has_not_text else None
        filters = dict(has_text=has_text, has_not_text=has_not_text)
        a = safe_tap(page, "a.link_menu", nth="random", filters=filters, delay=action_delay)
        return a.locator(".menu").text_content()


def _get_menu_boundary(page: Page) -> Locator:
    return page.locator(".list_section").first


def _get_menu_overlay(page: Page) -> Overlay:
    return dict(top = page.locator(".header_top").first.bounding_box()["height"])


###################################################################
################## Action 3 - :explore_articles: ##################
###################################################################

def explore_articles(
        page: Page,
        cafe_name: str,
        menu_name: str,
        visited: Set[ArticleId] = set(),
        model: ChatModel | None = None,
        prompt: str | Path | Prompt | None = None,
        temperature: float | None = 0.1,
        verbose: bool = False,
        **kwargs
    ) -> list[ArticleParams]:
    articles = list_articles(page, visited)
    if articles:
        return select_articles(cafe_name, menu_name, articles, model, prompt, temperature, verbose, **kwargs)
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

################## Action 9 - :navigate_article: ##################

def next_articles(page: Page, action_delay: Delay = (0.3, 0.6)):
    ranges = get_cafe_ranges(page, header=True, tab=True)
    delta = page.viewport_size["height"] - ranges["overlay"]["top"]
    safe_wheel(page, delta=delta, **ranges)
    wait(action_delay)


def reload_articles(page: Page, goto_delay: Delay = (1, 3)):
    page.reload(), wait(goto_delay)


###################################################################
#################### Action 4 - :goto_article: ####################
###################################################################

def goto_article(page: Page, id: str | int | Literal["random"], goto_delay: Delay = (1, 3)) -> bool:
    articles = locate_all(page, ".mainLink", **get_cafe_ranges(page, header=True, tab=True))
    if isinstance(id, int):
        articles[id].tap(), wait(goto_delay)
    if id == "random":
        random.choice(articles).tap(), wait(goto_delay)
        return True

    for article in articles:
        params = _parse_params(article.get_attribute("href") or str())
        if id == params["articleid"]:
            article.tap(), wait(goto_delay)
            return True
    return False


###################################################################
#################### Action 5 - :read_article: ####################
###################################################################

def read_article(page: Page, wait_until_read: bool = True, verbose: bool = False) -> Contents:
    lines, visible_lines = list(), list()
    isin_viewport, read_start, read_end, total = False, 0, 0, 0
    _, min_y, _, max_y = range_boundaries(page, **get_cafe_ranges(page, header=True, tab=False))

    selector = lambda tag: f'#postContent {tag}:not([style="display: none;"]):not(.se-module-oglink *)'
    for i, el in enumerate(locate_all(page, ", ".join([selector('p'), selector("img")]))):
        tag_name = el.evaluate("el => el.tagName")
        if tag_name == "img":
            line = f"![{el.get_attribute('alt') or '이미지'}]({el.get_attribute('src')})"
        else:
            line = el.text_content().replace('\u200b', '').strip()
        lines.append(line)

        if is_visible(el, min_y, max_y):
            if not isin_viewport:
                isin_viewport = True
                read_start = i
            visible_lines.append(line)
        elif isin_viewport:
            isin_viewport = False
            read_end = i
        total += 1
    read_done = ((read_end + 1) == total) if (total > 0) and visible_lines else True

    seconds = round(_estimate_reading_seconds(visible_lines), 1)
    if verbose:
        print(f"[글 읽기] {seconds}초 대기")
    if wait_until_read:
        wait(seconds)

    read_progress = dict(read_start=read_start, read_end=read_end, read_done=read_done)
    return dict(lines=lines, visible_lines=visible_lines, total=total, **read_progress)


def read_full_article(
        page: Page,
        wait_until_read: bool = True,
        verbose: bool = False,
        action_delay: Delay = (0.3, 0.6),
        timeout: float = 30.,
    ) -> Contents:
    start_time, end_time = time.perf_counter(), (lambda: time.perf_counter())
    contents = read_article(page, wait_until_read, verbose)
    read_start = contents["read_start"]

    while (not contents["read_done"]) and ((end_time() - start_time) < timeout):
        next_lines(page, action_delay)
        contents = read_article(page, wait_until_read, verbose)

    contents["read_start"] = read_start
    return contents


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

#################### Action 8 - :like_article: ####################

def like_article(page: Page):
    like_button = page.locator('.right_area [data-type="like"]').first
    if like_button.get_attribute("aria-pressed") == "false":
        like_button.tap()

################## Action 9 - :navigate_article: ##################

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
#################### Action 6 - :write_comment: ###################
###################################################################

def write_comment(
        page: Page,
        comment: str,
        action_delay: Delay = (0.3, 0.6),
        goto_delay: Delay = (1, 3),
        upload_delay: Delay = (2, 4),
        dry_run: bool = False,
    ):
    page.locator(".right_area .f_reply").first.tap(), wait(goto_delay)
    comment_area = page.locator(".comment_textarea").first
    comment_area.locator(".textarea_write").first.tap(), wait(action_delay)
    comment_area.locator(".text_input_area").first.type(comment, delay=100), wait(action_delay)
    if not dry_run:
        comment_area.locator(".btn_area > button", has_text="등록").tap()
    wait(upload_delay)
    go_back(page, goto_delay)


def read_comments(page: Page) -> list[str]:
    if page.locator(".CommonComment .num").first.text_content() != '0':
        comments = locate_all(page, ".comment_list .comment_content")
        return [comment.text_content() for comment in comments]
    else:
        return list()


###################################################################
########## Action 5+6 - :read_article_and_write_comment: ##########
###################################################################

def read_article_and_write_comment(
        page: Page,
        cafe_name: str,
        menu_name: str,
        action_delay: Delay = (0.3, 0.6),
        goto_delay: Delay = (1, 3),
        upload_delay: Delay = (2, 4),
        wait_until_read: bool = True,
        model: ChatModel | None = None,
        prompt: str | Path | Prompt | None = None,
        reasoning_effort: Literal["minimal","low","medium","high"] | None = "medium",
        verbose: bool = False,
        dry_run: bool = False,
        timeout: float = 30.,
        **kwargs
    ) -> tuple[ArticleData, Comment]:
    start_time, end_time = time.perf_counter(), (lambda: time.perf_counter())
    contents = read_article(page, wait_until_read=False, verbose=verbose)
    article_data = {
        "title": page.locator(".post_title .tit").first.text_content().strip(),
        "contents": contents["lines"],
        "comments": read_comments(page),
        "created_time": _to_iso_datetime(page.locator(".post_title .date").first.text_content().strip()),
        "current_time": dt.datetime.now().strftime("%Y-%m-%dT%H:%M") + "+09:00",
    }
    comment = create_comment(cafe_name, menu_name, article_data, model, prompt, reasoning_effort, verbose, **kwargs)

    if wait_until_read:
        current_wait = round(_estimate_reading_seconds(contents["visible_lines"]), 1)
        creating_time = round(time.perf_counter() - start_time, 1)
        left_wait = current_wait - creating_time
        if left_wait > 0.:
            wait(left_wait)

        while (not contents["read_done"]) and ((end_time() - start_time) < timeout):
            next_lines(page, action_delay)
            read_article(page, wait_until_read=True, verbose=verbose)

    if comment:
        write_comment(page, comment, action_delay, goto_delay, upload_delay, dry_run)
    return article_data, comment


def _to_iso_datetime(text: str) -> str:
    if (match := re.search(r"(\d{4}\.\d{2}\.\d{2}\. \d{2}:\d{2})", text)):
        try:
            datetime = dt.datetime.strptime(match.group(1), "%Y.%m.%d. %H:%M")
            return datetime.strftime("%Y-%m-%dT%H:%M") + "+09:00"
        except:
            return dt.datetime.now().strftime("%Y-%m-%dT%H:%M") + "+09:00"
    else:
        return dt.datetime.now().strftime("%Y-%m-%dT%H:%M") + "+09:00"


###################################################################
#################### Action 7 - :write_article: ###################
###################################################################

def write_article(page: Page):
    ...
