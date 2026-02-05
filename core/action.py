from __future__ import annotations

from playwright.sync_api import Page, Locator

from core.agent import Prompt4, Prompt5
from core.agent import ArticleParams, select_articles
from core.agent import ArticleInfo, create_comment
from core.agent import NewArticle, create_article

from utils.common import print_json, wait, Delay
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
    from typing import Iterable, Literal
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
    total_lines: int
    read_start: int
    read_end: int
    read_done: bool


class CafeNotFound(RuntimeError):
    ...


def cur_time() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + "+09:00"


def _to_iso_date(text: str) -> str:
    if (match := re.search(r"(\d{4}\.\d{2}\.\d{2}\.)", text)):
        try:
            datetime = dt.datetime.strptime(match.group(1), "%Y.%m.%d.")
            return datetime.strftime("%Y-%m-%d") + "T00:00:00+09:00"
        except:
            return cur_time()
    else:
        return cur_time()


def _to_iso_datetime(text: str) -> str:
    if (match := re.search(r"(\d{4}\.\d{2}\.\d{2}\. \d{2}:\d{2})", text)):
        try:
            datetime = dt.datetime.strptime(match.group(1), "%Y.%m.%d. %H:%M")
            return datetime.strftime("%Y-%m-%dT%H:%M") + ":00+09:00"
        except:
            return cur_time()
    else:
        return cur_time()


###################################################################
################### Action 0 - :goto_cafe_home: ###################
###################################################################

def goto_cafe_home(
        page: Page,
        mobile: bool = True,
        action_delay: Delay = (0.3, 0.6),
        goto_delay: Delay = (1, 3),
    ):
    """## Action 0"""
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


def goto_naver_main(
        page: Page,
        mobile: bool = True,
        goto_delay: Delay = (1, 3),
    ):
    if page.url != main_url(mobile):
        page.goto(main_url(mobile)), wait(goto_delay)


def main_url(mobile: bool) -> str:
    return f"https://{'m.' if mobile else 'www.'}naver.com"


def cafe_url(mobile: bool) -> str:
    if mobile:
        return "https://m.cafe.naver.com/"
    else:
        return "https://section.cafe.naver.com/ca-fe/home"


###################################################################
###################### Action 1 - :goto_cafe: #####################
###################################################################

def goto_cafe(
        page: Page,
        cafe_name: str,
        goto_delay: Delay = (1, 3),
    ):
    """## Action 1"""
    cafe_li = f'.mycafe_flicking:not([style="display: none;"]) a:has-text("{cafe_name}")'
    if page.locator(cafe_li).count() > 0:
        page.tap(cafe_li)
        return wait(goto_delay)

    my_cafe = '.area_flick_view a:has-text("내 카페")'
    if page.locator(my_cafe).count() > 0:
        page.tap(my_cafe), wait(goto_delay)
        cafe_li = f'.cafe_info:has-text("{cafe_name}")'
        if page.locator(cafe_li).count() > 0:
            ranges = dict(
                boundary = page.locator("body").first,
                overlay = dict(top=page.locator(".HeaderWrap").first.bounding_box()["height"]))
            safe_tap(page, cafe_li, **ranges)
            return wait(goto_delay)

    raise CafeNotFound(f"가입카페 목록에서 '{cafe_name}' 카페를 찾을 수 없습니다.")


def go_back(page: Page, goto_delay: Delay = (1, 3)):
    page.go_back(), wait(goto_delay)


def get_cafe_ranges(page: Page, header: bool = True, tab: bool = False) -> CafeRanges:
    return dict(
        boundary = page.locator("body").first,
        overlay = _get_cafe_overlay(page, header, tab),
    )


def _get_cafe_overlay(page: Page, header: bool = True, tab: bool = False) -> Overlay:
    try:
        header_height = page.locator(".WebHeader").first.bounding_box()["height"] if header else 0
    except Exception:
        header_height = 52
    try:
        tab_height = page.locator(".ArticleTab").first.bounding_box()["height"] if tab else 0
    except Exception:
        tab_height = 66
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
    """## Action 2"""
    open_menu(page, action_delay)
    if menu_name:
        safe_tap(page, f'a:has-text("{menu_name}")', delay=action_delay), wait(goto_delay)
        return menu_name
    else:
        has_text = re.compile('|'.join(has_text)) if has_text else None
        has_not_text = re.compile('|'.join(has_not_text)) if has_not_text else None
        filters = dict(has_text=has_text, has_not_text=has_not_text)
        a = safe_tap(page, "a.link_menu", nth="random", filters=filters, delay=action_delay)
        return a.locator(".menu").text_content()


def open_menu(page: Page, action_delay: Delay = (0.3, 0.6)):
    page.tap(f'header button:has-text("메뉴")'), wait(action_delay)


def _get_menu_boundary(page: Page) -> Locator:
    return page.locator(".list_section").first


def _get_menu_overlay(page: Page) -> Overlay:
    return dict(top = page.locator(".header_top").first.bounding_box()["height"])


###################################################################
################## Action 3 - :explore_articles: ##################
###################################################################

def explore_articles(
        page: Page,
        visited: set[ArticleId] = set(),
        prompt: Prompt4 = dict(),
        verbose: int | str | Path = 0,
        **kwargs
    ) -> list[ArticleParams]:
    """## Action 3"""
    articles = list_articles(page, visited)
    if articles:
        return select_articles(articles, **prompt, verbose=verbose, **kwargs) # Agent 1
    else:
        return list()


def list_articles(page: Page, visited: set[ArticleId] = set()) -> list[ArticleParams]:
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
    """## Action 4"""
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

def read_article(
        page: Page,
        wait_until_read: bool = True,
        verbose: int | str | Path = 0,
        contents_only: bool = False,
    ) -> ArticleInfo | Contents:
    """## Action 5"""
    lines, visible_lines = list(), list()
    isin_viewport, read_start, read_end = False, 0, 0
    _, min_y, _, max_y = range_boundaries(page, **get_cafe_ranges(page, header=True, tab=False))

    selector = lambda tag: f'#postContent {tag}:not([style="display: none;"]):not(.se-module-oglink *)'
    for i, el in enumerate(locate_all(page, ", ".join([selector('p'), selector("img")]))):
        tag_name = str(el.evaluate("el => el.tagName")).upper()
        if tag_name == "IMG":
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

    total_lines = len(lines)
    if isin_viewport and total_lines:
        read_end = total_lines - 1
    read_done = ((read_end + 1) == total_lines) if (total_lines > 0) and visible_lines else True

    seconds = round(_estimate_reading_seconds(visible_lines), 1)
    print_json({"action": "read_article", "reading_time": seconds}, verbose)
    if wait_until_read:
        wait(max(seconds, 0.1))

    if contents_only:
        keys = ["lines", "visible_lines", "total_lines", "read_start", "read_end", "read_done"]
        values = [lines, visible_lines, total_lines, read_start, read_end, read_done]
        return dict(zip(keys, values))
    else:
        return _make_article_info(page, lines)


def read_full_article(
        page: Page,
        action_delay: Delay = (0.3, 0.6),
        wait_until_read: bool = True,
        verbose: int | str | Path = 0,
        contents_only: bool = False,
        timeout: float = 30.,
    ) -> ArticleInfo | Contents:
    start_time, end_time = time.perf_counter(), (lambda: time.perf_counter())
    contents = read_article(page, wait_until_read, verbose, contents_only=True)
    read_start = contents["read_start"]

    while (not contents["read_done"]) and ((end_time() - start_time) < timeout):
        next_lines(page, action_delay)
        contents = read_article(page, wait_until_read, verbose, contents_only=True)
    if read_comments(page):
        ranges = get_cafe_ranges(page, header=True, tab=False)
        safe_wheel(page, target=page.locator(".CommonComment .write").first, **ranges), wait(action_delay)

    if contents_only:
        contents["read_start"] = read_start
        return contents
    else:
        return _make_article_info(page, contents["lines"])


def _make_article_info(page: Page, lines: list[str]) -> ArticleInfo:
    return {
        "title": page.locator(".post_title .tit").first.text_content().strip(),
        "contents": lines,
        "comments": read_comments(page),
        "created_at": _to_iso_datetime(page.locator(".post_title .date").first.text_content().strip()),
    }


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


###################################################################
#################### Action 6 - :like_article: ####################
###################################################################

def like_article(page: Page, action_delay: Delay = (0.3, 0.6)):
    """## Action 6"""
    like_button = page.locator('.right_area [data-type="like"]').first
    if like_button.get_attribute("aria-pressed") == "false":
        like_button.tap(), wait(action_delay)


###################################################################
#################### Action 7 - :write_comment: ###################
###################################################################

def write_comment(
        page: Page,
        comment: str,
        action_delay: Delay = (0.3, 0.6),
        goto_delay: Delay = (1, 3),
        upload_delay: Delay = (2, 4),
        dry_run: bool = False,
    ):
    """## Action 7"""
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
########## Action 5+7 - :read_article_and_write_comment: ##########
###################################################################

def read_article_and_write_comment(
        page: Page,
        comment_limit: str = "20자 이내",
        action_delay: Delay = (0.3, 0.6),
        goto_delay: Delay = (1, 3),
        upload_delay: Delay = (2, 4),
        wait_until_read: bool = True,
        prompt: Prompt5 = dict(),
        verbose: int | str | Path = 0,
        dry_run: bool = False,
        timeout: float = 30.,
        **kwargs
    ) -> tuple[ArticleInfo, Comment]:
    """## Action 5+7"""
    start_time, end_time = time.perf_counter(), (lambda: time.perf_counter())
    contents = read_article(page, wait_until_read=False, verbose=verbose, contents_only=True)
    article_info = _make_article_info(page, contents["lines"])
    comment = create_comment(article_info, comment_limit, **prompt, verbose=verbose, **kwargs) # Agent 2

    if wait_until_read:
        current_wait = round(_estimate_reading_seconds(contents["visible_lines"]), 1)
        creating_time = round(time.perf_counter() - start_time, 1)
        left_wait = current_wait - creating_time
        if left_wait > 0.:
            wait(left_wait)

        while (not contents["read_done"]) and ((end_time() - start_time) < timeout):
            next_lines(page, action_delay)
            contents = read_article(page, wait_until_read=True, verbose=verbose, contents_only=True)
        if article_info["comments"]:
            ranges = get_cafe_ranges(page, header=True, tab=False)
            safe_wheel(page, target=page.locator(".CommonComment .write").first, **ranges), wait(action_delay)

    if comment:
        write_comment(page, comment, action_delay, goto_delay, upload_delay, dry_run)
    return article_info, comment


###################################################################
#################### Action 8 - :write_article: ###################
###################################################################

def write_article(
        page: Page,
        articles: Iterable[ArticleInfo],
        my_articles: Iterable[str] = list(),
        title_limit: str = "30자 이내",
        contents_limit: str = "300자 이내",
        action_delay: Delay = (0.3, 0.6),
        goto_delay: Delay = (1, 3),
        upload_delay: Delay = (2, 4),
        prompt: Prompt5 = dict(),
        verbose: int | str | Path = 0,
        dry_run: bool = False,
        **kwargs
    ) -> NewArticle:
    """## Action 8"""
    page.locator(".FloatingWriteButton > button").first.tap(), wait(goto_delay)
    article = create_article(articles, my_articles, title_limit, contents_limit, **prompt, verbose=verbose, **kwargs)

    title_area = page.locator(".ArticleWriteFormSubject textarea").first
    title_area.tap(), wait(action_delay)
    title_area.type(article["title"], delay=100), wait(action_delay)

    content_area = page.locator("#one-editor article").first
    content_area.tap(), wait(action_delay)
    for line_no, content in enumerate(article["contents"]):
        if line_no > 0:
            page.keyboard.press("Enter"), wait(action_delay)
        if content:
            content_area.type(content, delay=100), wait(action_delay)

    if not dry_run:
        safe_tap(page, '.ArticleWriteComplete > [role="button"]', filters=dict(has_text="등록")), wait(upload_delay)

    return article


###################################################################
################## Action 9 - :read_my_articles: ##################
###################################################################

def read_my_articles(
        page: Page,
        goto_delay: Delay = (1, 3),
        n_articles: int | None = None,
        read_articles: bool = True,
        wait_until_read: bool = True,
        verbose: int | str | Path = 0,
    ) -> list[ArticleInfo]:
    """## Action 9"""
    data = list()
    for item in locate_all(page, ".list_area .txt_area")[:n_articles]:
        if read_articles:
            safe_tap(item, **_get_info_ranges(page)), wait(goto_delay)
            try:
                data.append(read_article(page, wait_until_read, verbose, contents_only=False))
            finally:
                go_back(page, goto_delay)
        else:
            data.append({
                "title": item.locator(".tit").text_content().strip(),
                "contents": list(),
                "comments": list(),
                "created_at": _to_iso_date(item.locator(".time").text_content().strip()),
            })
    return data


def open_info(page: Page, action_delay: Delay = (0.3, 0.6), goto_delay: Delay = (1, 3)):
    open_menu(page, action_delay)
    page.tap("header .info_link"), wait(goto_delay)


def close_info(page: Page, goto_delay: Delay = (1, 3)):
    page.tap('.HeaderGnbLeft [role="button"]'), wait(goto_delay)


def read_action_log(page: Page, action_delay: Delay = (0.3, 0.6), goto_delay: Delay = (1, 3)) -> dict[str,int]:
    open_menu(page, goto_delay)
    def safe_int(value: str) -> int:
        try: return int(value)
        except: return
    try:
        keys = [span.text_content().strip() for span in locate_all(page, ".myinfo_detail .detail_title")]
        values = [safe_int(span.text_content().strip()) for span in locate_all(page, ".myinfo_detail .detail_count")]
        return dict(zip(keys, values))
    finally:
        page.touchscreen.tap(0, 0), wait(action_delay)


def _get_info_ranges(page: Page) -> CafeRanges:
    return dict(
        boundary = page.locator("body").first,
        overlay = _get_info_overlay(page),
    )


def _get_info_overlay(page: Page) -> Overlay:
    return dict(top = page.locator(".HeaderWrap").first.bounding_box()["height"])
