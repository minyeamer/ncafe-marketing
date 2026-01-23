from __future__ import annotations

import openai

from typing import TypeVar, TypedDict, TYPE_CHECKING
from pathlib import Path
import json
import os
import random
import time

if TYPE_CHECKING:
    from typing import Iterable, Literal

ChatModel = TypeVar("ChatModel", bound=str)

class ArticleParams(TypedDict):
    clubid: str
    articleid: str
    boardtype: str
    menuid: str
    title: str

class ArticleData(TypedDict):
    title: str
    created_at: str
    contents: list[str]
    comments: list[str]

class Prompt(TypedDict, total=False):
    system: str
    user: str
    assistant: str | None


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
        system: str,
        user: str,
        assistant: str | None = None,
        verbose: bool = False,
        **kwargs
    ) -> str:
    start_time = time.perf_counter()
    response = openai.chat.completions.create(
        model = model,
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            *([{"role": "assistant", "content": assistant}] if assistant else []),
        ],
        **kwargs
    )
    content = response.choices[0].message.content
    if verbose:
        print(f"[질문하기] {round(time.perf_counter() - start_time, 1)}초 대기")
        print(content)
        print(f"[답변완료] 입력 토큰: {response.usage.prompt_tokens}, 출력 토큰: {response.usage.completion_tokens}")
    return content


def chat_json(
        model: str,
        system: str,
        user: str,
        assistant: str | None = None,
        verbose: bool = False,
        **kwargs
    ) -> dict | list:
    content = chat(model, system, user, assistant, verbose, **kwargs)
    try:
        return json.loads(content)
    except json.JSONDecodeError as error:
        print("JSON 파싱할 수 없습니다: ", content.replace('\n', ' '))
        raise error


###################################################################
#################### Agent 1: :select_articles: ###################
###################################################################

def select_articles(
        cafe_name: str,
        menu_name: str,
        articles: Iterable[ArticleParams],
        model: ChatModel | None = None,
        prompt: str | Path | Prompt | None = None,
        temperature: float | None = 0.1,
        verbose: bool = False,
        **kwargs
    ) -> list[ArticleParams]:
    """
    ### MARKDOWN FORMAT
    ```
    '${model}\\n---\\n${system-content}\\n---\\n${hint1}\\n---\\n${hint2}'
    ```
    ### INPUT FORMAT
    ```
    {
        "articles": [
            {"articleid": "131", "title": "제목1"},
            {"articleid": "242", "title": "제목2"},
            {"articleid": "353", "title": "제목3"}
        ],
        "hints": ["사례1", "사례2"]
    }
    ```
    ### OUTPUT FORMAT
    ```
    '131,353'
    ```
    """
    if not isinstance(prompt, dict):
        model, prompt = _build_select_articles_prompt(cafe_name, menu_name, articles, model, prompt)

    if isinstance(temperature, (float,int)):
        kwargs["temperature"] = temperature

    answer = chat(model or "gpt-4o-mini", **prompt, verbose=verbose, **kwargs)
    article_ids = answer.split(',')
    return [article for article in articles if article["articleid"] in article_ids]


def _build_select_articles_prompt(
        cafe_name: str,
        menu_name: str,
        articles: Iterable[ArticleParams],
        model: ChatModel | None = None,
        markdown_path: str | Path | None = None,
    ) -> tuple[ChatModel, Prompt]:
    markdown = read_file(markdown_path) if markdown_path else read_prompt(cafe_name, menu_name, "select_articles")
    sections = markdown.split("\n---\n")

    model = model if model else sections[0]
    system = sections[1].replace("${cafe_name}", cafe_name).replace("${menu_name}", menu_name)
    user = {"articles": [{"articleid": p["articleid"], "title": p["title"]} for p in articles], "hints": []}
    if len(sections) > 2:
        user["hints"] = sections[2:]

    return model, dict(system=system, user=json.dumps(user, ensure_ascii=False, separators=(',', ':')))


###################################################################
#################### Agent 2: :create_comment: ####################
###################################################################

def create_comment(
        cafe_name: str,
        menu_name: str,
        article_data: ArticleData,
        model: ChatModel | None = None,
        prompt: str | Path | Prompt | None = None,
        reasoning_effort: Literal["minimal","low","medium","high"] | None = "medium",
        verbose: bool = False,
        **kwargs
    ) -> str:
    """
    ### MARKDOWN FORMAT
    ```
    '${model}\\n---\\n${system-content}\\n---\\n${hint1}\\n---\\n${hint2}'
    ```
    ### INPUT FORMAT
    ```
    {
        "title": "제목",
        "contents": ["문장1", "이미지주소1", "문장2"],
        "comments": ["댓글1", "댓글2", "댓글3"],
        "created_time": "2026-01-02T12:04:05+09:00",
        "current_time": "2026-01-02T12:04:05+09:00",
        "hints": ["사례1", "사례2"]
    }
    ```
    ### OUTPUT FORMAT
    ```
    '댓글4'
    ```
    """
    if not isinstance(prompt, dict):
        model, prompt = _build_create_comment_prompt(cafe_name, menu_name, article_data, model, prompt)

    if isinstance(reasoning_effort, str):
        kwargs["reasoning_effort"] = reasoning_effort

    return chat(model or "gpt-5-mini", **prompt, verbose=verbose, **kwargs)


def _build_create_comment_prompt(
        cafe_name: str,
        menu_name: str,
        article_data: ArticleData,
        model: ChatModel | None = None,
        markdown_path: str | Path | None = None,
    ) -> tuple[ChatModel, Prompt]:
    markdown = read_file(markdown_path) if markdown_path else read_prompt(cafe_name, menu_name, "create_comment")
    sections = markdown.split("\n---\n")

    model = model if model else sections[0]
    system = sections[1].replace("${cafe_name}", cafe_name).replace("${menu_name}", menu_name)
    if len(sections) > 2:
        article_data["hints"] = sections[2:]
    else:
        article_data["hints"] = list()

    return model, dict(system=system, user=json.dumps(article_data, ensure_ascii=False, separators=(',', ':')))
