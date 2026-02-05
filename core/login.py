from __future__ import annotations

from playwright.sync_api import Page
from core.action import main_url, cafe_url, goto_naver_main, goto_cafe_home
from utils.common import wait, Delay

from typing import TYPE_CHECKING
import time

if TYPE_CHECKING:
    from typing import Literal


class NaverLoginError(RuntimeError):
    ...

class NaverLoginFailedError(NaverLoginError):
    ...

class WarningAccountError(NaverLoginError):
    ...

class ReCaptchaRequiredError(NaverLoginError):
    ...


def login(
        page: Page,
        userid: str,
        passwd: str,
        referer: Literal["main","cafe"] = "cafe",
        mobile: bool = True,
        action_delay: Delay = (0.3, 0.6),
        goto_delay: Delay = (1, 3),
    ):
    wander_around(page, mobile, goto_delay)
    login_begin(page, referer, mobile, action_delay, goto_delay)
    login_action(page, userid, passwd, mobile, action_delay, goto_delay)

    success_url = cafe_url(mobile) if referer == "cafe" else main_url(mobile)
    if get_page_url(page) != success_url:
        if page.locator("#error_message").count() > 0:
            message = page.locator("#error_message").first.text_content().strip()
            raise NaverLoginFailedError(message)
        elif page.locator("#divWarning").count() > 0:
            raise WarningAccountError("회원님의 아이디를 보호하고 있습니다.")
        elif page.locator("#rcapt").count() > 0:
            raise ReCaptchaRequiredError("자동입력 방지 문자를 입력해주세요.")
    goto_cafe_home(page, mobile, action_delay, goto_delay) # Action 0


def wander_around(page: Page, mobile: bool = True, goto_delay: Delay = (1, 3)):
    page.goto("https://www.google.com"), wait(goto_delay)
    page.goto(f"https://{'m.' if mobile else 'www.'}naver.com"), wait(goto_delay)


def login_begin(
        page: Page,
        referer: Literal["main","cafe"],
        mobile: bool = True,
        action_delay: Delay = (0.3, 0.6),
        goto_delay: Delay = (1, 3),
    ):
    if referer == "cafe":
        goto_cafe_home(page, mobile, action_delay, goto_delay) # Action 0
        if mobile:
            page.tap('.login_wrap a[role="button"]'), wait(goto_delay)
        else:
            page.click(".login_area a.login"), wait(goto_delay)
            # :has(a[href="https://cafe.naver.com"][target="_blank"])
            # return context.pages[-1]
    else:
        goto_naver_main(page, mobile, goto_delay)
        if mobile:
            page.tap('#MM_logo [class$="profile"]'), wait(goto_delay)
            page.tap('a[href^="https://nid.naver.com/nidlogin.login"]'), wait(goto_delay)
        else:
            page.click('#account a[href*="nidlogin"]'), wait(goto_delay)


def login_action(
        page: Page,
        userid: str,
        passwd: str,
        mobile: bool = True,
        action_delay: Delay = (0.3, 0.6),
        goto_delay: Delay = (1, 3),
    ):
    def type_value(selector: str, value: str):
        if mobile:
            page.tap(selector), wait(action_delay)
        else:
            page.click(selector), wait(action_delay)
        page.type(selector, value, delay=100), wait(action_delay)

    type_value("input#id", userid)
    type_value("input#pw", passwd)

    if mobile:
        page.tap("#submit_btn"), wait(goto_delay), wait(goto_delay)
    else:
        # if page.get_attribute("#smart_LEVEL", "value") == '1':
        #     safe_click(page, "#switch", position="center"), wait(action_delay) # IP보안
        page.click('button[type="submit"]'), wait(goto_delay)


def get_page_url(page: Page, timeout: float = 5., interval: float = 0.25) -> str:
    start_time = time.perf_counter()
    while (time.perf_counter() - start_time) < timeout:
        try:
            page.evaluate("() => window.location.href")
        except:
            time.sleep(interval)
    return str()
