from __future__ import annotations

import openai

from typing import TypeVar, TypedDict, TYPE_CHECKING
from pathlib import Path
import datetime as dt
import json
import os
import random
import time

if TYPE_CHECKING:
    from typing import Iterable, Literal

ChatModel = TypeVar("ChatModel", bound=str)

class Prompt(TypedDict):
    role: str
    content: str

class ArticleParams(TypedDict):
    clubid: str
    articleid: str
    boardtype: str
    menuid: str
    title: str

class ArticleInfo(TypedDict):
    title: str
    contents: list[str]
    comments: list[str]
    created_at: str

class NewArticle(TypedDict):
    title: str
    contents: list[str]
    type: int
    emotion: int
    created_at: str


KEY_PATH = "env/api.key"

MODELS = {"gpt-4o-mini", "gpt-5-mini"}

SYSTEM_PROMPTS = {
    "select_articles": "env/select_articles.md"
}


def read_file(path: str | Path) -> str:
    if isinstance(path, Path) or os.path.isfile(path):
        with open(path, 'r', encoding="utf-8") as file:
            return file.read()
    elif isinstance(path, str):
        return path
    else:
        return str()


def set_api_key(api_key: str | Path | None = None):
    openai.api_key = read_file(api_key if api_key else Path(KEY_PATH)).strip()


def read_prompt(cafe_name: str, menu_name: str, agent_name: str, root: str = "env") -> str:
    cafe_path = os.path.join(root, cafe_name)
    menu_path = os.path.join(cafe_path, menu_name)
    if not os.path.exists(menu_path):
        menu_path = random.choice([path for path in os.listdir(cafe_path) if os.path.isdir(path)])

    file_path = os.path.join(menu_path, agent_name + ".md")
    return read_file(file_path)


def chat(
        model: ChatModel,
        messages: list[str],
        verbose: bool = False,
        **kwargs
    ) -> str:
    start_time = time.perf_counter()
    response = openai.chat.completions.create(model=model, messages=messages, **kwargs)
    content = response.choices[0].message.content
    if verbose:
        print(f"[추론 시간] {round(time.perf_counter() - start_time, 1)}초 대기")
        print(f"[응답 결과] {content}")
        print(f"[사용 토큰] 입력: {response.usage.prompt_tokens}, 출력: {response.usage.completion_tokens}")
    return content


def chat_json(
        model: str,
        messages: list[str],
        verbose: bool = False,
        **kwargs
    ) -> dict | list:
    content = chat(model, messages, verbose, **kwargs)
    try:
        return json.loads(content)
    except json.JSONDecodeError as error:
        print("[JSONDecodeError] JSON 파싱할 수 없습니다: ", content.replace('\n', ' '))
        raise error


def min_json(data: dict | list) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'), default=str)


###################################################################
#################### Agent 1: :select_articles: ###################
###################################################################

def select_articles(
        cafe_name: str,
        menu_name: str,
        articles: Iterable[ArticleParams],
        model: ChatModel | None = None,
        messages: str | Path | list[Prompt] | None = None,
        temperature: float | None = 0.1,
        verbose: bool = False,
        **kwargs
    ) -> list[ArticleParams]:
    """
    ### MARKDOWN FORMAT
    ```
    '${model}\\n<--->\\n${system-content}\\n<--->\\n${user-content}\\n${assistant-content}'
    ```
    ### INPUT FORMAT
    ```
    [
        {"articleid": "131", "title": "제목1"},
        {"articleid": "242", "title": "제목2"},
        {"articleid": "353", "title": "제목3"}
    ]
    ```
    ### OUTPUT FORMAT
    ```
    ["131","242"]
    ```
    """
    if not isinstance(messages, list):
        model, messages = _build_select_articles_prompt(cafe_name, menu_name, articles, model, messages)
    if verbose:
        print("[사용자 입력] {}".format(messages[-1]["content"]))

    if isinstance(temperature, (float,int)):
        kwargs["temperature"] = temperature

    try:
        article_ids = set(chat_json(model or "gpt-4o-mini", messages, verbose=verbose, **kwargs))
        return [article for article in articles if article["articleid"] in article_ids]
    except Exception as e:
        if verbose:
            print(f"[{type(e)}] {e}")
    return str()


def _build_select_articles_prompt(
        cafe_name: str,
        menu_name: str,
        articles: Iterable[ArticleParams],
        model: ChatModel | None = None,
        markdown_path: str | Path | None = None,
    ) -> tuple[ChatModel, list[Prompt]]:
    markdown = read_file(markdown_path) if markdown_path else read_prompt(cafe_name, menu_name, "select_articles")
    sections = markdown.split("\n<--->\n")
    model = model if model else sections[0]
    messages = [{"role": "system", "content": sections[1]}]

    for section in sections[2:]:
        try:
            user, assistant = section.split('\n')
        except ValueError:
            continue
        messages += [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]

    articles = [{"articleid": article["articleid"], "title": article["title"]}
                for article in articles if not is_question(article["title"])]
    messages.append({"role": "user", "content": min_json(articles)})

    return model, messages


def is_question(title: str) -> bool:
    return title.endswith('?') or ("추천" in title)


###################################################################
#################### Agent 2: :create_comment: ####################
###################################################################

def create_comment(
        cafe_name: str,
        menu_name: str,
        article_info: ArticleInfo,
        model: ChatModel | None = None,
        messages: str | Path | list[Prompt] | None = None,
        reasoning_effort: Literal["minimal","low","medium","high"] | None = "high",
        verbose: bool = False,
        **kwargs
    ) -> str:
    """
    ### MARKDOWN FORMAT
    ```
    '${model}\\n<--->\\n${system-content}\\n<--->\\n${user-content}\\n${assistant-content}'
    ```
    ### INPUT FORMAT
    ```
    {
        "title": "제목",
        "contents": ["문장1", "![alt](url)", "문장2"],
        "comments": ["댓글1", "댓글2"],
        "created_at": "2026-01-02T12:04:05+09:00",
        "current_time": "2026-01-02T12:04:05+09:00"
    }
    ```
    ### OUTPUT FORMAT
    ```
    {"comment":null,"reject_reason":null,"violation_reason":null}
    ```
    """
    if not isinstance(messages, list):
        model, messages = _build_create_comment_prompt(cafe_name, menu_name, article_info.copy(), model, messages)
    if verbose:
        print("[사용자 입력] {}".format(messages[-1]["content"]))

    if isinstance(reasoning_effort, str):
        kwargs["reasoning_effort"] = reasoning_effort

    try:
        comment = chat_json(model or "gpt-5-mini", messages, verbose=verbose, **kwargs)
        if comment.get("comment") and not (comment.get("reject_reason") or comment.get("violation_reason")):
            return comment["comment"]
    except Exception as e:
        if verbose:
            print(f"[{type(e)}] {e}")
    return str()


def _build_create_comment_prompt(
        cafe_name: str,
        menu_name: str,
        article_info: ArticleInfo,
        model: ChatModel | None = None,
        markdown_path: str | Path | None = None,
    ) -> tuple[ChatModel, list[Prompt]]:
    markdown = read_file(markdown_path) if markdown_path else read_prompt(cafe_name, menu_name, "create_comment")
    sections = markdown.split("\n<--->\n")
    model = model if model else sections[0]
    messages = [{"role": "system", "content": sections[1]}]

    for section in sections[2:]:
        try:
            user, assistant = section.split('\n')
        except ValueError:
            continue
        messages += [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]

    article_info["current_time"] = (dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + "+09:00")
    messages.append({"role": "user", "content": min_json(article_info)})

    return model, messages


###################################################################
#################### Agent 3: :create_article: ####################
###################################################################

def create_article(
        cafe_name: str,
        menu_name: str,
        articles: Iterable[ArticleInfo],
        history: Iterable[str] = list(),
        model: ChatModel | None = None,
        messages: str | Path | list[Prompt] | None = None,
        reasoning_effort: Literal["minimal","low","medium","high"] | None = "high",
        verbose: bool = False,
        **kwargs
    ) -> NewArticle:
    """
    ### MARKDOWN FORMAT
    ```
    '${model}\\n<--->\\n${system-content}\\n<--->\\n${user-content}\\n${assistant-content}'
    ```
    ### INPUT FORMAT
    ```
    {
        "articles": [{
            "title": "제목",
            "contents": ["문장1", "![alt](url)", "문장2"],
            "comments": ["댓글1", "댓글2"],
            "created_at": "2026-01-02T12:04:05+09:00"
        }],
        "history": [{
            "title": "제목",
            "contents": ["문장1", "![alt](url)", "문장2"],
            "comments": ["댓글1", "댓글2"],
            "created_at": "2026-01-02T12:04:05+09:00"
        }],
        "current_time": "2026-01-02T12:04:05+09:00"
    }
    ```
    ### OUTPUT FORMAT
    ```
    {"title":"제목","contents":["문장1","문장2"],"type":null,"emotion":null,"violation_reason":null}
    ```
    """
    if not isinstance(messages, list):
        model, messages = _build_create_article_prompt(cafe_name, menu_name, articles, history, model, messages)

    if isinstance(reasoning_effort, str):
        kwargs["reasoning_effort"] = reasoning_effort

    try:
        article = chat_json(model or "gpt-5-mini", messages, verbose=verbose, **kwargs)
        if not article.get("violation_reason"):
            article["created_at"] = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + "+09:00"
            return article
    except Exception as e:
        if verbose:
            print(f"[{type(e)}] {e}")
    return dict()


def _build_create_article_prompt(
        cafe_name: str,
        menu_name: str,
        articles: Iterable[ArticleInfo],
        history: Iterable[str] = list(),
        model: ChatModel | None = None,
        markdown_path: str | Path | None = None,
    ) -> tuple[ChatModel, Prompt]:
    markdown = read_file(markdown_path) if markdown_path else read_prompt(cafe_name, menu_name, "create_article")
    sections = markdown.split("\n<--->\n")
    model = model if model else sections[0]
    messages = [{"role": "system", "content": sections[1]}]

    for section in sections[2:]:
        try:
            user, assistant = section.split('\n')
        except ValueError:
            continue
        messages += [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]

    data = {
        "articles": list(articles),
        "history": history,
        "current_time": (dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + "+09:00")
    }
    messages.append({"role": "user", "content": min_json(data)})

    return model, messages
