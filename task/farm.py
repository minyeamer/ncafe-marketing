from __future__ import annotations

from core.browser import BrowserController

from core.login import login, NaverLoginError
from core.login import WarningAccountError, ReCaptchaRequiredError, NaverLoginFailedError

from core.action import goto_cafe_home, goto_cafe, goto_menu, CafeNotFound
from core.action import goto_article, explore_articles
from core.action import reload_articles, next_articles, go_back
from core.action import read_article, read_full_article, read_article_and_write_comment
from core.action import like_article, write_article
from core.action import read_my_articles, open_info, close_info, read_action_log

from core.agent import set_api_key, KEY_PATH, PROMPTS_ROOT

from extensions.gsheets import WorksheetClient, ServiceAccount, ACCOUNT_PATH
from extensions.vpn import VpnClient, VpnConfig, VpnRuntimeError
from extensions.vpn import VpnLoginFailedError, VpnInUseError, VpnFailedError
from extensions.vpn import WindowNotFoundError, ElementNotFoundError

from utils.common import AttrDict, Delay, wait, print_json
from utils.timer import ActionTimer

from typing import get_type_hints, Literal, TypeVar, TypedDict, TYPE_CHECKING
from collections import defaultdict, deque
import datetime as dt
import json

from pathlib import Path
import os
import random
import sys
import traceback

if TYPE_CHECKING:
    from typing import Any
    from core.action import ArticleId, ArticleInfo, Comment, NewArticle
    from extensions.gsheets import WorksheetConnection

class QuiteHours(TypedDict):
    start: int
    end: int


SECRETS_ROOT = ".secrets"
STATES_ROOT = os.path.join(SECRETS_ROOT, "states")
MOBILE_DEVICE = "Galaxy S24"

LOGS_ROOT = ".logs"

DEFAULTS = {
    "account": ACCOUNT_PATH,
    "openai_key": KEY_PATH,
}

def is_default(value: Any) -> bool:
    return isinstance(value, str) and (value == ":default:")


class MaxLoopExceeded(RuntimeError):
    ...

class PromptNotFoundError(RuntimeError):
    ...

class QuietHoursError(RuntimeError):
    ...


class MaxRetries(TypedDict, total=False):
    task_loop: int
    action_loop: int
    vpn_connect: int


###################################################################
####################### Task Config - Farmer ######################
###################################################################

class Config(TypedDict):
    row_no: int
    userid: str
    passwd: str
    ip_addr: str
    cafe_name: str
    menu_name: str
    read_count: str
    comment_count: str
    comment_delay: int
    article_count: str
    article_delay: int
    like_count: str
    visit_limit: int
    comment_limit: int
    comment_length: str
    title_length: str
    contents_length: str

class ActionCount(TypedDict):
    read: int
    comment: int
    article: int
    like: int

class ActionDelay(TypedDict):
    visit: int
    comment: int
    article: int

class ActionLimit(TypedDict):
    visit: int
    comment: int

class WordLength(TypedDict):
    title: str
    contents: str
    comment: str


class ConfigWrapper(AttrDict):

    def __init__(self, config: Config = dict(), **kwargs):
        super().__init__()
        self.row_no = config["row_no"]
        self.userid = config["userid"]
        self.passwd = config["passwd"]
        self.ip_addr = config["ip_addr"]
        self.cafe_name = config["cafe_name"]
        self.menu_name = config["menu_name"]

        def safe_int(value: int | str) -> int:
            try: return int(value)
            except: return 0

        def randint(value: str) -> int:
            return random.randint(*map(safe_int, value.split('~', 1))) if '~' in str(value) else safe_int(value)

        counter: ActionCount = {key[:-len("_count")]: randint(config[key]) for key in config.keys() if key.endswith("_count")}
        self.counter, self.__counter = counter.copy(), counter.copy()

        self.delay: ActionDelay = {key[:-len("_delay")]: safe_int(config[key]) for key in config.keys() if key.endswith("_delay")}
        self.limit: ActionLimit = {key[:-len("_limit")]: safe_int(config[key]) for key in config.keys() if key.endswith("_limit")}
        self.length: WordLength = {key[:-len("_length")]: config[key] for key in config.keys() if key.endswith("_length")}

        self.qualified: bool = None
        self.__done: bool = None

    @property
    def done(self) -> bool:
        if not self.__done:
            self.__done = ((self.counter["comment"] == 0) and (self.counter["like"] == 0) and ((self.counter["article"] == 0)))
            return self.__done
        else:
            return True

    def calc_counter(self, key: Literal["read","comment","article","like"]) -> int:
        return self.__counter.get(key, 0) - self.counter.get(key, 0)

    def reset_counter(self, key: Literal["all","read","comment","article","like"]):
        if key == "all":
            self.counter[key] = {key: self.__counter.get(key, 0) for key in self.counter.keys()}
        else:
            self.counter[key] = self.__counter.get(key, 0)

    def sub_counter(self, key: Literal["all","read","comment","article","like"]):
        if key == "all":
            self.counter[key] = {key: (self.counter[key] - 1) for key in self.counter.keys()}
        else:
            self.counter[key] = self.counter[key] - 1

    def zero_counter(self, key: Literal["all","read","comment","article","like"]):
        if key == "all":
            self.counter[key] = {key: 0 for key in self.counter.keys()}
            self.__done = True
        else:
            self.counter[key] = 0

    def get_left_keys(self) -> list[str]:
        return [key for key, count in self.counter.items() if count > 0]


class ActionThreshold(AttrDict):

    def __init__(self, comment: float = 0.3, like: float = 0.4):
        super().__init__()
        self.comment = comment
        self.like = like


###################################################################
######################## Task Log - Farmer ########################
###################################################################

Index = TypeVar("Index", bound=int)
UserId = TypeVar("UserId", bound=str)
StopTask = TypeVar("StopTask", bound=bool)

class ArticleActivity(TypedDict):
    title: str
    contents: list[str]
    comments: list[str]
    created_at: str
    written_comment: Comment
    like_this: bool


ErrorFlag = Literal[
    "VPN 로그인 오류", "VPN 사용중", "VPN 접속 오류", "VPN 확인 불가", "VPN 조작 오류",
    "네이버 비밀번호 불일치", "네이버 계정 보호조치", "네이버 CAPTCHA 발생", "네이버 로그인 오류",
    "가입카페 확인 불가", "반복 횟수 초과", "금지 시간대", "브라우저 조작 오류"]

class ErrorLog(TypedDict):
    type: str
    message: str
    exc_info: str
    flag: ErrorFlag | None


class TaskLog(AttrDict):

    def __init__(self):
        self.last_active_ts: dt.datetime | None = None
        self.time_on_cafe: float | None = None
        self.visit_count: int | None = None
        self.article_count: int | None = None
        self.comment_count: int | None = None
        self.read_ids: set[ArticleId] = set()
        self.read_articles: list[ArticleActivity] = list()
        self.my_articles: deque[ArticleInfo] = deque()
        self.written_articles: list[NewArticle] = list()
        self.total_steps: int = 0
        self.error: ErrorLog | None = None

    def to_json(self, ellipsis_list: bool = False) -> dict:
        def serialize(kv: tuple[str, Any]) -> tuple[str, Any]:
            if kv[0] == "last_active_ts":
                ts = (kv[1].strftime("%Y-%m-%dT%H:%M:%S")+"+09:00") if isinstance(kv[1], dt.datetime) else None
                return kv[0], ts
            elif kv[0] == "read_ids":
                return kv[0], ','.join(kv[1])
            elif kv[0] in ("read_articles", "my_articles", "written_articles"):
                return kv[0], len(kv[1]) if ellipsis_list else list(kv[1])
            else:
                return kv
        return dict(map(serialize, self.items()))


class LogTableRow(TypedDict):
    row_no: int
    userid: str
    cafe_name: str
    menu_name: str
    ip_addr: str
    last_active_ts: dt.datetime
    time_on_cafe: float
    visit_count: int
    article_count: int
    comment_count: int
    read_ids: str
    read_articles: int
    new_article_count: int
    new_comment_count: int
    new_like_count: int
    total_steps: int
    error_flag: ErrorFlag


###################################################################
###################### Task Executor - Farmer #####################
###################################################################

class Farmer(BrowserController):

    def __init__(
            self,
            configs: WorksheetConnection,
            openai_key:  str | Path | Literal[":default:"] = ":default:",
            device: str = str(),
            mobile: bool = True,
            headless: bool = True,
            action_delay: Delay = (0.3, 0.6),
            goto_delay: Delay = (1, 3),
            reload_delay: Delay = (10, 12),
            upload_delay: Delay = (2, 4),
            quiet_hours: QuiteHours = dict(),
            comment_threshold: float = 0.3,
            like_threshold: float = 0.4,
            vpn_config: VpnConfig = dict(),
            write_config: WorksheetConnection = dict(),
            **kwargs
        ):
        super().__init__(device, mobile, headless, action_delay, goto_delay, reload_delay, upload_delay)

        self.quiet_hours = quiet_hours
        self.check_quiet_hours()

        self.validate_worksheet_connection(configs, empty=False)
        self.configs = self.read_configs_from_gsheets(**configs)

        set_api_key(DEFAULTS["openai_key"] if is_default(openai_key) else openai_key)

        self.index: Index = 0
        self.logs: dict[Index, TaskLog] = defaultdict(TaskLog)
        self.timers: dict[Index, ActionTimer] = defaultdict(ActionTimer)
        self.threshold = ActionThreshold(comment_threshold, like_threshold)

        self.set_vpn_client(vpn_config)

        self.validate_worksheet_connection(write_config, empty=True)
        self.write_config = write_config

    @property
    def config(self) -> ConfigWrapper:
        return self.configs[self.index]

    @property
    def log(self) -> TaskLog:
        return self.logs[self.index]

    @property
    def timer(self) -> ActionTimer:
        return self.timers[self.index]

    @property
    def delays2(self) -> dict[str,Delay]:
        return self.delays.get_delays(["action", "goto"])

    @property
    def delays3(self) -> dict[str,Delay]:
        return self.delays.get_delays(["action", "goto", "upload"])

    @property
    def browser_state(self) -> Path | None:
        states_root = Path(STATES_ROOT)
        states_root.mkdir(parents=True, exist_ok=True)
        return states_root / (self.config.userid + ".json")

    def check_quiet_hours(self):
        if self.quiet_hours:
            hour = dt.datetime.now().hour
            if self.quiet_hours["start"] <= hour <= self.quiet_hours["end"]:
                raise QuietHoursError("실행 금지 시간대입니다.")

    ########################### Entry Point ###########################

    def start(
            self,
            max_retries: MaxRetries = dict(),
            num_my_articles: int = 10,
            max_read_length: int = 500,
            reload_start_step: int = 10,
            wait_until_read: bool = True,
            task_delay: float = 5.,
            vpn_delay: float = 5.,
            with_state: bool = True,
            verbose: int | str | Path = 0,
            dry_run: bool = False,
            save_log: bool = True,
            **kwargs
        ):
        self.check_quiet_hours()

        if self.vpn_enabled:
            self.vpn.start_process(self.vpn_config.force_restart)
            if not self.vpn.try_login(**self.vpn_config.login):
                self.vpn.restart_service(**self.vpn_config.login)

        stop_task: StopTask = None

        for _ in range(max_retries.get("task_loop") or 10):
            if stop_task or all([config.done for config in self.configs]):
                break

            if isinstance(stop_task, bool):
                comment_min_delay = self.min_action_delay("comment")
                article_min_delay = self.min_action_delay("article")
                delay = max(task_delay, min(comment_min_delay, article_min_delay))

                self.print_loop("wait", verbose, seconds=delay)
                wait(delay)

            stop_task = self.task_loop(
                max_retries, num_my_articles, max_read_length, reload_start_step,
                wait_until_read, vpn_delay, with_state, verbose, dry_run, save_log)

            if self.write_config:
                try:
                    self.write_log_table_to_gsheets(**self.write_config)
                except:
                    pass

        if self.vpn_enabled:
            self.vpn.terminate_process()

    def min_action_delay(self, key: Literal["comment","article"]) -> float:
        delays = [max(0., self.configs[index].delay[key] - secs)
            for index, timer in self.timers.items()
                if isinstance(secs := timer.get_elapsed_time(key), float)]
        return min(delays) if delays else 0.

    ############################# <start> #############################
    ############################ Task Loop ############################

    def task_loop(
            self,
            max_retries: MaxRetries = dict(),
            num_my_articles: int = 10,
            max_read_length: int = 500,
            reload_start_step: int = 10,
            wait_until_read: bool = True,
            vpn_delay: float = 5.,
            with_state: bool = True,
            verbose: int | str | Path = 0,
            dry_run: bool = False,
            save_log: bool = True,
        ) -> StopTask:
        stop_task, flag = False, None
        max_steps = max_retries.get("action_loop") or 100
        max_vpn_retries = max_retries.get("vpn_connect") or 5

        for i in range(len(self.configs)):
            self.index = i

            if self.config.done:
                continue
            elif stop_task:
                self.print_loop("break", verbose)
                self.config.zero_counter("all")
                continue

            state = self.browser_state if with_state else None
            self.print_loop("start", verbose, state=state)
            vpn_connected = False

            try:
                self.check_quiet_hours()

                if self.vpn_enabled and (ip_addr := self.config.ip_addr):
                    vpn_connected = self.ensure_vpn_connected(ip_addr, max_vpn_retries, vpn_delay)

                try:
                    self.do_actions(
                        max_steps, num_my_articles, max_read_length, reload_start_step,
                        wait_until_read, verbose, dry_run, state=state)
                    self.log.error = None
                finally:
                    if vpn_connected:
                        self.vpn.disconnect(**self.vpn_config.wait_options)
                        self.vpn.logout(**self.vpn_config.wait_options)
            except Exception as error:
                self.log.error = dict(
                    type = str(type(error).__name__),
                    message = self.get_error_msg(error),
                    exc_info = '\n'.join(traceback.format_exception(*sys.exc_info())),
                    flag = (flag := self.get_error_flag(error)),
                )

            self.log.last_active_ts = dt.datetime.now()
            self.log.time_on_cafe = self.timer.end_timer("visit", 3)
            self.print_loop("end", verbose)

            if save_log:
                self.save_log_json()

            stop_task = self.handle_error_flag(flag)

            if (not stop_task) and vpn_connected:
                wait(vpn_delay)

        return stop_task

    @BrowserController.with_browser
    def do_actions(
            self,
            max_steps: int = 100,
            num_my_articles: int = 10,
            max_read_length: int = 500,
            reload_start_step: int = 10,
            wait_until_read: bool = True,
            verbose: int | str | Path = 0,
            dry_run: bool = False,
            *,
            state: str | Path | None = None,
        ):
        self.navigate_to_menu(has_state=(bool(state) and os.path.exists(str(state))))

        qualified = self.check_member_level()
        self.config.qualified = qualified

        if not qualified:
            self.config.zero_counter("article")
        elif self.need_my_articles((n := num_my_articles)):
            self.log.my_articles = deque(self.read_my_articles(n), maxlen=n)

        try:
            self.action_loop(max_steps, max_read_length, reload_start_step, wait_until_read, verbose, dry_run)
            self.config.qualified = self.check_member_level()
        finally:
            if not qualified:
                self.config.reset_counter("article")

    ############################# <start> #############################
    ########################### Action Loop ###########################

    def action_loop(
            self,
            max_steps: int = 100,
            max_read_length: int = 500,
            reload_start_step: int = 10,
            wait_until_read: bool = True,
            verbose: int | str | Path = 0,
            dry_run: bool = False,
        ):
        articles, step, unselected_steps = list(), 1, 0

        for step in range(1, max_steps+1):
            self.check_quiet_hours()

            if not self.has_next_action():
                break

            if step > reload_start_step:
                wait(self.delays.reload)
                reload_articles(self.page, self.delays.goto)
            elif step > 2:
                next_articles(self.page, self.delays.action)

            selected = explore_articles(
                self.page, self.log.read_ids, self.get_prompt("select_articles"), verbose) # Action 3 + Agent 1
            for params in selected:
                self.check_quiet_hours()

                if goto_article(self.page, params["articleid"], self.delays.goto): # Action 4
                    try:
                        activity = self.read_and_react(max_read_length, wait_until_read, verbose, dry_run)
                        if activity:
                            articles.append({key: activity[key] for key in ["title","contents","comments","created_at"]})
                            self.log.read_articles.append(activity)
                    finally:
                        go_back(self.page, self.delays.goto)

                if self.is_article_allowed():
                    new_article = self.write_article(articles, verbose, dry_run)
                    self.log.written_articles.append(new_article)

            read_ids = ','.join([param["articleid"] for param in selected])
            self.print_loop(step, verbose, read_ids=read_ids)

            if (step > reload_start_step) and (not selected):
                wait(max(10, (unselected_steps := unselected_steps + 1)))
            else:
                unselected_steps = 0

            self.log.total_steps += 1

    def get_prompt(self, file_name: str) -> dict:
        cafe_root = os.path.join(PROMPTS_ROOT, self.config.cafe_name)
        cafe_menu_root = os.path.join(cafe_root, self.config.menu_name)
        for root in [cafe_menu_root, cafe_root, PROMPTS_ROOT]:
            markdown_path = os.path.join(root, f"{file_name}.md")
            if os.path.exists(markdown_path):
                return dict(markdown_path=markdown_path)
        raise PromptNotFoundError(f"'{file_name}' 프롬프트가 존재하지 않습니다.")

    ########################### Action 0+1+2 ##########################

    def navigate_to_menu(self, has_state: bool = True):
        if has_state:
            goto_cafe_home(self.page, self.mobile, **self.delays2) # Action 0
        else:
            login(self.page, self.config.userid, self.config.passwd, "cafe", self.mobile, **self.delays2)
        wait(self.delays.goto)

        goto_cafe(self.page, self.config.cafe_name, self.delays.goto), wait(self.delays.goto) # Action 1
        self.timer.start_timer("visit")
        goto_menu(self.page, self.config.menu_name, **self.delays2), wait(self.delays.goto) # Action 2

    ############################# Action 9 ############################

    def check_member_level(self) -> bool:
        qualified = True
        action_log = read_action_log(self.page, **self.delays2)

        if "방문" in action_log:
            self.log.visit_count = action_log["방문"]
            if self.config.limit["visit"]:
                qualified &= (self.config.limit["visit"] <= action_log["방문"])

        if "작성글" in action_log:
            self.log.article_count = action_log["작성글"]

        if "댓글" in action_log:
            self.log.comment_count = action_log["댓글"]
            if self.config.limit["comment"]:
                qualified &= (self.config.limit["comment"] <= action_log["댓글"])

        return qualified

    def read_my_articles(self, n: int = 10) -> list[ArticleInfo]:
        open_info(self.page, **self.delays2)
        try:
            return read_my_articles(self.page, self.delays.goto, n, wait_until_read=False) # Action 9
        finally:
            close_info(self.page, self.delays.goto)

    ######################### Action Condition ########################

    def has_next_action(self) -> bool:
        return ((self.config.counter["like"] > 0)
            or ((self.config.counter["comment"] > 0)
                and self.timer.gte("comment", self.config.delay["comment"]))
            or ((self.config.counter["article"] > 0)
                and self.timer.gte("article", self.config.delay["article"])))

    def is_comment_allowed(self) -> bool:
        return ((self.config.counter["comment"] > 0)
            and self.timer.gte("comment", self.config.delay["comment"])
            and (random.uniform(0, 1) > self.threshold.comment))

    def is_article_allowed(self) -> bool:
        return ((self.config.counter["read"] < 1)
            and (self.config.counter["article"] > 0)
            and self.timer.gte("article", self.config.delay["article"]))

    def is_like_allowed(self) -> bool:
        return (self.config.counter["like"] > 0) and (random.uniform(0, 1) > self.threshold.like)

    def need_my_articles(self, num_my_articles: int = 10) -> bool:
        return ((num_my_articles > 0)
            and (self.config.counter["article"] > 0)
            and (self.log.article_count > 0)
            and (not self.log.my_articles))

    ########################### Action 5+6+7 ##########################

    def read_and_react(
            self,
            max_read_length: int = 500,
            wait_until_read: bool = True,
            verbose: int | str | Path = 0,
            dry_run: bool = False,
        ) -> ArticleActivity | None:
        word_count = read_article(self.page, wait_until_read=False, contents_only=True)["word_count"]
        if word_count > max_read_length:
            return None
        else:
            comment: Comment = None
            common = dict(page=self.page, wait_until_read=wait_until_read, verbose=verbose)

        if self.is_comment_allowed():
            article, comment = read_article_and_write_comment(
                **common,
                comment_limit = (self.config.length["comment"] or "20자 이내"),
                prompt = self.get_prompt("create_comment"),
                dry_run = dry_run,
                **self.delays3,
            ) # Action 5+7 & Agent 2
            if comment:
                self.config.sub_counter("comment")
                self.timer.start_timer("comment")
        else:
            article = read_full_article(**common, action_delay=self.delays.action) # Action 5
        self.config.sub_counter("read")
        article["written_comment"] = comment

        if self.is_like_allowed():
            if not dry_run:
                like_article(self.page, self.delays.action) # Action 6
            self.config.sub_counter("like")
            article["like_this"] = True
        else:
            article["like_this"] = False

        return article

    ############################# Action 8 ############################

    def write_article(
            self,
            articles: list[ArticleInfo],
            verbose: int | str | Path = 0,
            dry_run: bool = False,
            update: bool = True,
        ) -> NewArticle:
        info, new = dict(title=str(), contents=list(), comments=list(), created_at=str()), dict()
        try:
            new = write_article(
                page = self.page,
                articles = articles,
                my_articles = self.log.my_articles,
                title_limit = (self.config.length["title"] or "30자 이내"),
                contents_limit = (self.config.length["contents"] or "300자 이내"),
                prompt = self.get_prompt("create_article"),
                verbose = verbose,
                dry_run = dry_run,
                **self.delays3,
            ) # Action 8
        finally:
            go_back(self.page, self.delays.goto)
        self.timer.start_timer("article")

        self.config.reset_counter("read")
        self.config.sub_counter("article")

        if self.log.my_articles.maxlen and update:
            for key in ["title", "contents", "created_at"]:
                if key in new:
                    info[key] = new[key]
            self.log.my_articles.appendleft(info)
        return new

    ########################### Action Loop ###########################
    ############################## <end> ##############################

    ############################ Task Loop ############################
    ############################## <end> ##############################

    ########################### Handle Error ##########################

    def get_error_msg(self, error: Exception) -> str:
        try:
            return str(error) or None
        except:
            return None

    def get_error_flag(self, error: Exception) -> ErrorFlag | None:
        if isinstance(error, VpnRuntimeError):
            if isinstance(error, VpnLoginFailedError):
                return "VPN 로그인 오류"
            elif isinstance(error, VpnInUseError):
                return "VPN 사용중"
            elif isinstance(error, VpnFailedError):
                return "VPN 접속 오류"
            else:
                return "VPN 오류"
        elif isinstance(error, WindowNotFoundError):
            return "VPN 확인 불가"
        elif isinstance(error, ElementNotFoundError):
            return "VPN 조작 오류"
        elif isinstance(error, NaverLoginError):
            if isinstance(error, NaverLoginFailedError):
                return "네이버 계정 불일치"
            elif isinstance(error, WarningAccountError):
                return "네이버 계정 보호조치"
            elif isinstance(error, ReCaptchaRequiredError):
                return "네이버 CAPTCHA 발생"
            else:
                return "네이버 로그인 오류"
        elif isinstance(error, CafeNotFound):
            return "가입카페 확인 불가"
        elif isinstance(error, MaxLoopExceeded):
            return "반복 횟수 초과"
        elif isinstance(error, QuietHoursError):
            return "금지 시간대"
        elif isinstance(error, TimeoutError):
            return "브라우저 조작 오류"
        else:
            return None

    def handle_error_flag(self, flag: ErrorFlag) -> StopTask:
        if not isinstance(flag, str):
            return False
        elif flag == "VPN 사용중":
            try:
                self.vpn.restart_service(**self.vpn_config.login)
                self.config.zero_counter("all")
                return False
            except Exception:
                return True
        elif flag.startswith("네이버") or (flag == "가입카페 확인 불가"):
            userid = self.config.userid
            for config in self.configs:
                if config.userid == userid:
                    config.zero_counter("all")
            if flag.startswith("네이버") and (state := self.browser_state) and state.exists():
                os.remove(str(state))
            return False
        else:
            return flag.startswith("VPN") or (flag == "금지 시간대")

    ############################# Task Log ############################

    def print_loop(
            self,
            step: int | Literal["start","end","break","wait"],
            verbose: int | str | Path = 0,
            **kwargs
        ):
        common = lambda: dict(
            index = self.index,
            userid = self.config.userid,
            cafe_name = self.config.cafe_name,
            menu_name = self.config.menu_name,
        )

        if isinstance(step, int):
            body = dict(
                task_step = f"loop_{step}",
                **common(),
                read_ids = str(read_ids) if (read_ids := kwargs.get("read_ids")) else None,
                counter = self.config.counter,
                timer = self.timer.get_all_elapsed_times(ndigits=3),
            )
        elif step == "start":
            body = dict(
                task_step = "loop_start",
                **common(),
                config = self.config,
                state = str(state) if (state := kwargs.get("state")) else None,
            )
        elif step == "wait":
            body = dict(
                task_step = "loop_wait",
                seconds = kwargs.get("seconds"),
            )
        else:
            body = dict(
                task_step = f"loop_{step}",
                **common(),
                log = self.log.to_json(ellipsis_list=((not isinstance(verbose, int)) or (verbose < 3))),
            )

        print_json(body, verbose)

    def save_log_json(self):
        logs_path = Path(LOGS_ROOT) / self.config.userid
        logs_path.mkdir(parents=True, exist_ok=True)
        with open(logs_path / (dt.datetime.now().strftime("%Y%m%d%H%M%S")+".json"), 'w', encoding="utf-8") as file:
            json.dump(self.log.to_json(), file, indent=2, ensure_ascii=False, default=str)

    ########################## Read and Write #########################

    def read_configs_from_gsheets(
            self,
            key: str,
            sheet: str,
            account: str | Path | Literal[":default:"] = ":default:",
            head: int = 1,
        ) -> list[ConfigWrapper]:
        client = WorksheetClient(self._get_credentials(account), key, sheet, head)
        str_keys = [i for i, type in enumerate(get_type_hints(Config).values(), start=1) if type == str]
        records = client.get_all_records(numericise_ignore=str_keys)
        return [ConfigWrapper(record) for record in records if isinstance(record["row_no"], int)]

    def write_log_table_to_gsheets(
            self,
            key: str,
            sheet: str,
            account: str | Path | Literal[":default:"] = ":default:",
            head: int = 1,
        ):
        client = WorksheetClient(self._get_credentials(account), key, sheet, head)
        records = self.make_log_table()
        client.overwrite_worksheet(records)

    def make_log_table(self) -> list[LogTableRow]:
        rows = list()
        for index, log in self.logs.items():
            config = self.configs[index]
            rows.append(dict(
                row_no = config.row_no,
                userid = config.userid,
                cafe_name = config.cafe_name,
                menu_name = config.menu_name,
                ip_addr = config.ip_addr,
                last_active_ts = log.last_active_ts,
                time_on_cafe = log.time_on_cafe,
                visit_count = log.visit_count,
                article_count = log.article_count,
                comment_count = log.comment_count,
                read_ids = ','.join(sorted(log.read_ids)) or None,
                read_articles = len(log.read_articles),
                new_article_count = len(log.written_articles),
                new_comment_count = len([1 for activity in log.read_articles if activity["written_comment"]]),
                new_like_count = len([1 for activity in log.read_articles if activity["like_this"]]),
                total_steps = log.total_steps,
                error_flag = log.error["flag"] if log.error else None,
            ))
        return rows

    def validate_worksheet_connection(self, conn: WorksheetConnection, empty: bool = False) -> bool:
        if not isinstance(conn, dict):
            raise TypeError("구글시트 연결 정보가 올바른 타입이 아닙니다.")
        elif empty and (not conn):
            return True
        elif not (conn.get("key") and conn.get("sheet")):
            raise KeyError("구글시트 연결 정보에 'key' 또는 'sheet' 값이 없습니다.")
        return True

    def _get_credentials(self, account: str | Path | Literal[":default:"] = ":default:",) -> ServiceAccount:
        return ServiceAccount(DEFAULTS["account"] if is_default(account) else str(account))

    ########################## VPN Extension ##########################

    @property
    def vpn(self) -> VpnClient:
        if self.__vpn is not None:
            return self.__vpn
        else:
            raise RuntimeError("VPN 클라이언트가 초기화되지 않았습니다.")

    def set_vpn_client(self, vpn_config: VpnConfig = dict()):
        if vpn_config:
            config = vpn_config if isinstance(vpn_config, VpnConfig) else VpnConfig(**vpn_config)
            self.__vpn = VpnClient(**config)
            self.vpn_config = config
            self.vpn_enabled = True
        else:
            self.__vpn = None
            self.vpn_config = None
            self.vpn_enabled = False

    def ensure_vpn_connected(self, ip_addr: str, max_vpn_retries: int = 5, vpn_delay: float = 5.) -> bool:
        for step in range(1, max_vpn_retries+1):
            try:
                self.vpn.try_login(**self.vpn_config.login)
                if self.vpn.search_and_connect(ip_addr, **self.vpn_config.connect):
                    return True
            except Exception:
                self.vpn.start_process(force_restart=True)
                wait(vpn_delay * step)
        raise VpnFailedError("VPN이 연결되지 않았습니다.")
