from __future__ import annotations

from core.browser import BrowserController
from core.login import login
from core.action import goto_cafe_home, goto_cafe, goto_menu
from core.action import goto_article, explore_articles
from core.action import reload_articles, next_articles, go_back
from core.action import read_article_and_write_comment, read_full_article
from core.action import like_article, write_article
from core.action import read_my_articles, open_info, close_info, read_action_log
from core.agent import set_api_key, KEY_PATH, PROMPTS_ROOT

from utils.common import AttrDict, Delay, wait, print_json
from utils.gsheets import WorksheetClient, ServiceAccount, ACCOUNT_PATH
from utils.timer import ActionTimer

from typing import get_type_hints, TypeVar, TypedDict, TYPE_CHECKING
from collections import defaultdict, deque
from pathlib import Path
import datetime as dt
import json
import os
import random

if TYPE_CHECKING:
    from typing import Any, Callable, Literal, Sequence
    from core.action import ArticleId, ArticleInfo, Comment, NewArticle


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


###################################################################
####################### Task Config - Farmer ######################
###################################################################

class Config(TypedDict):
    userid: str
    passwd: str
    enabled: bool
    cafe_name: str
    menu_name: str
    visit_delay: int
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
        self.userid = config["userid"]
        self.passwd = config["passwd"]
        self.cafe_name = config["cafe_name"]
        self.menu_name = config["menu_name"]

        def randint(value: str) -> int:
            return random.randint(*map(int, value.split('~', 1))) if '~' in value else int(value)

        counter: ActionCount = {key[:-len("_count")]: randint(config[key]) for key in config.keys() if key.endswith("_count")}
        self.counter, self.__counter = counter.copy(), counter.copy()

        self.delay: ActionDelay = {key[:-len("_delay")]: config[key] for key in config.keys() if key.endswith("_delay")}
        self.limit: ActionLimit = {key[:-len("_limit")]: config[key] for key in config.keys() if key.endswith("_limit")}
        self.length: WordLength = {key[:-len("_length")]: config[key] for key in config.keys() if key.endswith("_length")}

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


class ActionThreshold(AttrDict):

    def __init__(self, comment: float = 0.3, like: float = 0.4):
        super().__init__()
        self.comment = comment
        self.like = like


###################################################################
######################## Task Log - Farmer ########################
###################################################################

UserId = TypeVar("UserId", bound=str)

class ArticleActivity(TypedDict):
    title: str
    contents: list[str]
    comments: list[str]
    created_at: str
    written_comment: Comment
    like_this: bool


class TaskLog(AttrDict):

    def __init__(self):
        self.time_on_cafe: float | None = None
        self.last_active_ts: dt.datetime | None = None
        self.visit_count: int | None = None
        self.article_count: int | None = None
        self.comment_count: int | None = None
        self.read_ids: set[ArticleId] = set()
        self.read_articles: list[ArticleActivity] = list()
        self.my_articles: deque[ArticleInfo] = deque()
        self.written_articles: list[NewArticle] = list()

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


###################################################################
###################### Task Executor - Farmer #####################
###################################################################

class Farmer(BrowserController):

    def __init__(
            self,
            sheet_key: str,
            sheet_name: str,
            account: ServiceAccount | Literal[":default:"] = ":default:",
            openai_key:  str | Path | Literal[":default:"] = ":default:",
            device: str = str(),
            mobile: bool = True,
            headless: bool = True,
            action_delay: Delay = (0.3, 0.6),
            goto_delay: Delay = (1, 3),
            reload_delay: Delay = (3, 5),
            upload_delay: Delay = (2, 4),
            comment_threshold: float = 0.3,
            like_threshold: float = 0.4,
        ):
        super().__init__(device, mobile, headless, action_delay, goto_delay, reload_delay, upload_delay)
        self.credentials = ServiceAccount(DEFAULTS["account"] if is_default(account) else account)
        self.configs = self.read_configs_from_gsheets(sheet_key, sheet_name)
        self.threshold = ActionThreshold(comment_threshold, like_threshold)
        self.index = 0
        self.__logs: dict[UserId, TaskLog] = defaultdict(TaskLog)
        self.__timers: dict[UserId, ActionTimer] = defaultdict(ActionTimer)
        set_api_key(DEFAULTS["openai_key"] if is_default(openai_key) else openai_key)

    @property
    def config(self) -> ConfigWrapper:
        return self.configs[self.index]

    @property
    def userid(self) -> str:
        return self.config.userid

    @property
    def log(self) -> TaskLog:
        return self.__logs[self.userid]

    @property
    def timer(self) -> ActionTimer:
        return self.__timers[self.userid]

    @property
    def delays2(self) -> dict[str,Delay]:
        return self.delays.get_delays(["action", "goto"])

    @property
    def delays3(self) -> dict[str,Delay]:
        return self.delays.get_delays(["action", "goto", "upload"])

    def read_configs_from_gsheets(self, key: str, sheet: str) -> list[ConfigWrapper]:
        client = WorksheetClient(self.credentials, key, sheet)
        str_keys = [i for i, type in enumerate(get_type_hints(Config).values(), start=1) if type == str]
        records = client.get_all_records(head=2, numericise_ignore=str_keys)
        return [ConfigWrapper(record) for record in records if record["enabled"]]

    def start(
            self,
            has_state: bool = True,
            max_steps: int = 100,
            num_my_articles: int = 10,
            verbose: int | str | Path = 0,
            dry_run: bool = False,
            save_log: bool = True,
            **kwargs
        ):
        for i in range(len(self.configs)):
            self.index = i
            if has_state:
                states_root = Path(STATES_ROOT)
                states_root.mkdir(parents=True, exist_ok=True)
                kwargs["state"] = states_root / (self.userid + ".json")

            print_json(dict(
                task_step = "loop_start",
                index = self.index,
                userid = self.userid,
                config = self.config,
                state = str(kwargs.get("state"))), verbose)

            try:
                self.do_actions(has_state, max_steps, num_my_articles, verbose, dry_run, **kwargs)
            finally:
                self.log.time_on_cafe = self.timer.end_timer("visit", 3)
                self.log.last_active_ts = dt.datetime.now()

            print_json(dict(
                task_step = "loop_end",
                index = self.index,
                userid = self.userid,
                log = self.log.to_json(ellipsis_list=((not isinstance(verbose, int)) or (verbose < 3)))), verbose)

            if save_log:
                self.save_log_json()

    @BrowserController.with_browser
    def do_actions(
            self,
            has_state: bool = True,
            max_steps: int = 100,
            num_my_articles: int = 10,
            verbose: int | str | Path = 0,
            dry_run: bool = False,
            **kwargs
        ):
        self.navigate_to_menu(has_state)
        if not self.check_member_level():
            self.config.zero_counter("article")

        if self.need_my_articles((n := num_my_articles)):
            self.log.my_articles = deque(self.read_my_articles(n), maxlen=n)

        self.action_loop(max_steps, verbose, dry_run)

        if self.check_member_level():
            self.config.reset_counter("article")

    def save_log_json(self):
        logs_path = Path(LOGS_ROOT) / self.userid
        logs_path.mkdir(parents=True, exist_ok=True)
        with open(logs_path / (dt.datetime.now().strftime("%Y%m%d%H%M%S")+".json"), 'w', encoding="utf-8") as file:
            json.dump(self.log.to_json(), file, indent=2, ensure_ascii=False, default=str)

    ############################ Loop Start ###########################

    def action_loop(
            self,
            max_steps: int = 100,
            verbose: int | str | Path = 0,
            dry_run: bool = False,
        ):
        root = os.path.join(PROMPTS_ROOT, self.config.cafe_name, self.config.menu_name)
        prompt = lambda agent: dict(markdown_path=os.path.join(root, f"{agent}.md"))
        articles, step, unselected_steps = list(), 0, 0

        while self.has_next_action():
            if step >= max_steps:
                raise MaxLoopExceeded(f"[{self.userid}] 최대 루프 횟수에 도달했습니다.")
            elif step > 10:
                wait(self.delays.reload)
                reload_articles(self.page, self.delays.goto)
            elif step > 1:
                next_articles(self.page, self.delays.action)
            step += 1

            selected = explore_articles(self.page, self.log.read_ids, prompt("select_articles"), verbose) # Action 3 + Agent 1
            for params in selected:
                if goto_article(self.page, params["articleid"], self.delays.goto): # Action 4
                    try:
                        activity = self.read_and_react(prompt, verbose, dry_run)
                        articles.append({key: activity[key] for key in ["title","contents","comments","created_at"]})
                        self.log.read_articles.append(activity)
                    finally:
                        go_back(self.page, self.delays.goto)

                if self.is_article_allowed():
                    new_article = self.write_article(articles, prompt, verbose, dry_run)
                    self.log.written_articles.append(new_article)

            print_json(dict(
                task_step = f"loop_{step}",
                index = self.index,
                userid = self.userid,
                read_ids = ','.join([param["articleid"] for param in selected]),
                counter = self.config.counter,
                timer = self.timer.get_all_elapsed_times(ndigits=3)), verbose)

            if (step > 10) and (not selected):
                unselected_steps += 1
                wait(5 * (unselected_steps * 0.5))
            else:
                unselected_steps = 0

    ########################### Action 0+1+2 ##########################

    def navigate_to_menu(self, has_state: bool = True):
        if has_state:
            goto_cafe_home(self.page, self.mobile, **self.delays2) # Action 0
        else:
            login(self.page, self.userid, self.config.passwd, mobile=self.mobile, **self.delays2)
        wait(self.delays.goto)

        goto_cafe(self.page, self.config.cafe_name, self.delays.goto), wait(self.delays.goto) # Action 1
        self.timer.start_timer("visit")
        goto_menu(self.page, self.config.menu_name, **self.delays2), wait(self.delays.goto) # Action 2

    ############################# Action 9 ############################

    def check_member_level(self) -> bool:
        qualified = True
        action_log = read_action_log(self.page)

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
        return ((self.config.counter["comment"] > 0)
            or (self.config.counter["like"] > 0)
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
            prompt: Callable,
            verbose: int | str | Path = 0,
            dry_run: bool = False,
        ) -> ArticleActivity:
        comment: Comment = None
        if self.is_comment_allowed():
            article, comment = read_article_and_write_comment(
                page = self.page,
                comment_limit = (self.config.length["comment"] or "20자 이내"),
                prompt = prompt("create_comment"),
                verbose = verbose,
                dry_run = dry_run,
                **self.delays3,
            ) # Action 5+7 & Agent 2
            if comment:
                self.config.sub_counter("comment")
                self.timer.start_timer("comment")
        else:
            article = read_full_article(self.page, self.delays.action, verbose=verbose) # Action 5
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
            prompt: Callable,
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
                prompt = prompt("create_article"),
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

    ############################# Loop End ############################
