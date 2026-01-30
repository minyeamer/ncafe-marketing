from __future__ import annotations

from core.browser import BrowserController
from core.home import goto_cafe_home
from core.login import login
from core.action import goto_cafe, goto_menu, goto_article, explore_articles
from core.action import reload_articles, next_articles
from core.action import read_article_and_write_comment, read_full_article, go_back
from core.action import like_article, write_article, read_history, ArticleInfo
from core.action import open_info, close_info, parse_action_log
from core.agent import set_api_key, PROMPTS_ROOT

from utils.common import Delay, wait
from utils.gsheets import WorksheetClient, ACCOUNT_PATH

from typing import get_type_hints, TypeVar, TypedDict, TYPE_CHECKING
from collections import defaultdict
import datetime as dt
import os
import time
import random

if TYPE_CHECKING:
    from typing import Any, Callable, Hashable, Literal
    from utils.gsheets import ServiceAccount
    _KT = TypeVar("_KT", Hashable)
    _VT = TypeVar("_VT", Any)
    JsonString = TypeVar("JsonString", str)
    Path = TypeVar("Path", str)


SECRETS_ROOT = ".secrets"
STATES_ROOT = os.path.join(SECRETS_ROOT, "states")
MOBILE_DEVICE = "Galaxy S24"


class Config(TypedDict):
    userid: str
    passwd: str
    enabled: bool
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
    comment: int
    article: int

class ActionLimit(TypedDict):
    visit: int
    comments: int

class WordLength(TypedDict):
    title: str
    contents: str
    comment: str


class ConfigWrapper(dict):
    counter: ActionCount = dict()
    delay: ActionDelay = dict()
    limit: ActionLimit = dict()
    length: WordLength = dict()

    def __init__(self, config: Config = dict(), **kwargs):
        super().__init__()
        self.userid = config["userid"]
        self.passwd = config["passwd"]
        self.cafe_name = config["cafe_name"]
        self.menu_name = config["menu_name"]

        def randint(value: str) -> int:
            return random.randint(*map(int, value.split('~', 1))) if '~' in value else int(value)

        counter = {key: randint(self[key]) for key in self.keys() if (key in self) and str(key).endswith("_count")}
        self.counter, self.__counter = counter.copy(), counter.copy()
        self.delay = {key: self[key] for key in self.keys() if (key in self) and str(key).endswith("_delay")}
        self.limit = {key: self[key] for key in self.keys() if (key in self) and str(key).endswith("_limit")}
        self.length = {key: self[key] for key in self.keys() if (key in self) and str(key).endswith("_length")}

    def reset_counter(self, key: Literal["read","comment","article","like"]):
        self.counter[key] = self.__counter.get(key, 0)

    def sub_counter(self, key: Literal["read","comment","article","like"]):
        self.counter[key] = self.counter[key] - 1

    def zero_counter(self, key: Literal["read","comment","article","like"]):
        self.counter[key] = 0

    def calc_counter(self, key: Literal["read","comment","article","like"]) -> int:
        return self.__counter.get(key, 0) - self.counter.get(key, 0)

    def get_left_keys(self) -> list[str]:
        return [key for key, count in self.counter.items() if count > 0]


class ActionTimer(dict):

    def start_timer(self, key: _KT):
        self.update({key: time.perf_counter()})

    def end_timer(self, key: _KT, ndigits: int | None = None) -> float | None:
        try:
            return self.get_elapsed_time(key, ndigits)
        finally:
            self.pop(key, None)

    def get_elapsed_time(self, key: _KT, ndigits: int | None = None) -> float | None:
        if key in self:
            elapsed_time = time.perf_counter() - self[key]
            return round(elapsed_time, ndigits) if ndigits else elapsed_time
        else:
            return None

    def gte(self, key: _KT, value: float) -> bool:
        if (key in self) and isinstance(value, (float,int)):
            return (time.perf_counter() - self[key]) >= value
        else:
            return True


class Farmer(BrowserController):
    user_info: dict[str,dict] = dict()

    def __init__(
            self,
            sheet_key: str,
            sheet_name: str,
            account: ServiceAccount | Literal[":default:"] = ":default:",
            openai_key:  str | Path | None = None,
            device: str = str(),
            mobile: bool = True,
            headless: bool = False,
            action_delay: Delay = (0.3, 0.6),
            goto_delay: Delay = (1, 3),
            upload_delay: Delay = (2, 4),
        ):
        super().__init__(device, mobile, headless, action_delay, goto_delay, upload_delay)
        account = ACCOUNT_PATH if isinstance(account, str) and (account == ":default:") else account
        self.credentials = ServiceAccount(account)
        self.configs = self.read_configs_from_gsheets(sheet_key, sheet_name)
        self.index = 0
        self.logs = defaultdict(dict)
        self.visited = defaultdict(set)
        self.timer = ActionTimer()
        set_api_key(openai_key)

    @property
    def config(self) -> ConfigWrapper:
        return self.configs[self.index]

    @property
    def userid(self) -> str:
        return self.userid

    @property
    def delays2(self) -> dict[str,Delay]:
        return self.delays.get_delays(["action", "goto"])

    @property
    def delays3(self) -> dict[str,Delay]:
        return self.delays.get_delays(["action", "goto", "upload"])

    def read_configs_from_gsheets(self, key: str, sheet: str) -> list[ConfigWrapper]:
        client = WorksheetClient(self.credentials, key, sheet)
        str_keys = [i for i, _, type in enumerate(get_type_hints(Config).items(), start=1) if type == str]
        records = client.get_all_records(head=2, numericise_ignore=str_keys)
        return [ConfigWrapper(record) for record in records if record["enabled"]]

    def run(self, has_state: bool = True, verbose: int = 0, **kwargs):
        for i in range(len(self.configs)):
            self.index = i
            if has_state:
                kwargs["state"] = os.path.join(STATES_ROOT, self.userid)

            self.timer.start_timer((self.userid, "visit"))
            try:
                self.do_actions(has_state=has_state, verbose=verbose, **kwargs)
            finally:
                self.logs[self.userid]["time_on_cafe"] = self.timer.end_timer((self.userid, "visit"), 0)
                self.logs[self.userid]["last_active_ts"] = dt.datetime.now()

    ########################### Action Start ##########################

    @BrowserController.with_browser
    def do_actions(
            self,
            has_state: bool = True,
            verbose: int = 0,
            dry_run: bool = False,
            max_steps: int = 100,
            **kwargs
        ):
        root = os.path.join(PROMPTS_ROOT, self.config.cafe_name, self.config.menu_name)
        prompt = lambda agent: dict(markdown_path=os.path.join(root, f"{agent}.md"))
        articles, visited, step = list(), set(), 0

        self.navigate_to_menu(has_state)
        if not self.check_member_level():
            self.config.zero_counter("article")

        history = self.read_history_top10() if self.config.counter["article"] > 0 else list()
        unselected_steps = 0.

        while self.has_next_action():
            if step >= max_steps:
                raise
            elif step > 10:
                reload_articles(self.page, self.delays.goto)
            elif step > 1:
                next_articles(self.page, self.delays.action)

            selected = explore_articles(self.page, visited, prompt("select_articles"), verbose)
            for params in selected: # Action 3
                if goto_article(self.page, params["articleid"], self.delays.goto): # Action 4
                    try:
                        article = self.read_and_react(prompt, verbose, dry_run)
                        articles.append(article)
                    finally:
                        go_back(self.page, self.delays.goto)

                if self.is_article_allowed():
                    new_article = write_article(
                        page = self.page,
                        articles = articles,
                        history = history,
                        title_limit = self.config.length["title"],
                        contents_limit = self.config.length["contents"],
                        prompt = prompt("create_article"),
                        verbose = verbose,
                        **self.delays3,
                    ) # Action 8
                    self.config.reset_counter("read")
                    self.timer.start_timer((self.userid, "article"))
                    return new_article

            if (step > 10) and (not selected):
                unselected_steps += 1
                wait(5 * (unselected_steps * 0.5))
            else:
                unselected_steps = 0

            step += 1

    ############################ Action 1+2 ###########################

    def navigate_to_menu(self, has_state: bool = True):
        if has_state:
            goto_cafe_home(self.page, self.mobile, **self.delays2)
        else:
            login(self.page, self.userid, self.config.passwd, mobile=self.mobile, **self.delays2)

        goto_cafe(self.page, self.config.cafe_name, self.delays.goto) # Action 1
        goto_menu(self.page, self.config.menu_name, **self.delays2) # Action 2

    ############################# Action 9 ############################

    def check_member_level(self) -> bool:
        open_info(self.page, **self.delays2)
        is_over_limit = True
        try:
            action_log = parse_action_log(self.page)

            if "방문" in action_log:
                self.logs[self.userid]["visit"] = action_log["방문"]
                if self.config.limit["visit"]:
                    is_over_limit &= self.config.limit["visit"] <= action_log["방문"]

            if "작성글" in action_log:
                self.logs[self.userid]["article"] = action_log["작성글"]

            if "댓글" in action_log:
                self.logs[self.userid]["comments"] = action_log["댓글"]
                if self.config.limit["comments"]:
                    is_over_limit &= self.config.limit["comments"] <= action_log["댓글"]

            return is_over_limit
        finally:
            close_info(self.page, self.delays.goto)


    def read_history_top10(self, n_articles: int = 10) -> list[ArticleInfo]:
        open_info(self.page, **self.delays2)
        try:
            return read_history(self.page, self.delays.goto, n_articles, wait_until_read=False)
        finally:
            close_info(self.page, self.delays.goto)

    ######################### Action Condition ########################

    def has_next_action(self) -> bool:
        return ((self.config.counter["comment"] > 0)
            or (self.config.counter["like"] > 0)
            or ((self.config.counter["article"] > 0)
                and self.timer.gte((self.userid, "article"), self.config.delay["article"])))

    def is_comment_allowed(self, threshold: float = 0.3) -> bool:
        return ((self.config.counter["comment"] > 0)
            and self.timer.gte((self.userid, "comment"), self.config.delay["comment"])
            and (random.uniform(0, 1) > threshold))

    def is_article_allowed(self) -> bool:
        return ((self.config.counter["read"] < 1)
            and (self.config.counter["article"] > 0)
            and self.timer.gte((self.userid, "article"), self.config.delay["article"]))

    def is_like_allowed(self, threshold: float = 0.5) -> bool:
        return (self.config.counter["like"] > 0) and (random.uniform(0, 1) > threshold)

    ########################### Action 5+6+7 ##########################

    def read_and_react(self, prompt: Callable, verbose: int = 0, dry_run: bool = False) -> ArticleInfo:
        if self.is_comment_allowed():
            article, comment = read_article_and_write_comment(
                page = self.page,
                comment_limit = self.config.length["comment"],
                prompt = prompt("create_comment"),
                verbose = verbose,
                dry_run = dry_run,
                **self.delays3,
            ) # Action 5+7
            if comment:
                self.config.sub_counter("comment")
                self.timer.start_timer((self.userid, "comment"))
        else:
            article = read_full_article(self.page, self.delays.action, verbose=verbose) # Action 5
        self.config.sub_counter("read")

        if self.is_like_allowed():
            if not dry_run:
                like_article(self.page, self.delays.action) # Action 6
            self.config.sub_counter("like")

        return article

    ############################ Action End ###########################
