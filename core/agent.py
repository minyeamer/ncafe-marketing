from __future__ import annotations

import openai

from typing import TypeVar, TypedDict, TYPE_CHECKING
from pathlib import Path
import json
import os

if TYPE_CHECKING:
    from typing import Iterable

ChatModel = TypeVar("ChatModel", bound=str)

class ArticleParams(TypedDict):
    clubid: str
    articleid: str
    boardtype: str
    menuid: str
    title: str

class ArticleContext(ArticleParams):
    expected: str

class Prompts(TypedDict, total=False):
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


def chat(model: ChatModel, system: str, user: str, assistant: str | None = None, **kwargs) -> str:
    response = openai.chat.completions.create(
        model = model,
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            *([{"role": "assistant", "content": assistant}] if assistant else []),
        ],
        **kwargs
    )
    return response.choices[0].message.content


def chat_json(model: str, system: str, user: str, assistant: str | None = None, **kwargs) -> dict | list:
    content = chat(model, system, user, assistant, **kwargs)
    return json.loads(content)


###################################################################
#################### Agent 1: :select_articles: ###################
###################################################################

def select_articles(
        articles: Iterable[ArticleParams],
        cafe_name: str,
        menu_name: str,
        model: ChatModel | None = None,
        prompts: str | Path | Prompts | None = None,
        temperature: float | None = 0.1,
        **kwargs
    ) -> list[ArticleContext]:
    """
    ### MARKDOWN FORMAT
    "${**model**}\\n---\\n${**system-content**}\\n---\\n${**assistant-content**}"
    ### INPUT FORMAT
    '[{"articleid": "1", "title": "제목1"}, {"articleid": "2", "title": "제목2"}, {"articleid": "3", "title": "제목3"}]'
    ### OUTPUT FORMAT
    '[{"articleid": "1", "title": "제목1", "expected": "댓글1"}, {"articleid": "3", "title": "제목3", "expected": "댓글3"}]'
    """
    if not isinstance(prompts, dict):
        markdown = read_file(prompts if prompts else Path(SYSTEM_PROMPTS["select_articles"]))
        model, system, assistant = markdown.split("\n---\n", maxsplit=2)
        prompts = dict(
            system = system.replace("${cafe_name}", cafe_name).replace("${menu_name}", menu_name),
            user = json.dumps([dict(articleid=x["articleid"], title=x["title"]) for x in articles], ensure_ascii=False),
            assistant = assistant.replace('\n', ' '),
        )

    if isinstance(temperature, (float,int)):
        kwargs["temperature"] = temperature

    selected = chat_json(model or "gpt-4o-mini", **prompts, **kwargs)
    params = {article["articleid"]: article for article in articles}
    return [dict(params[id], **article) for article in selected if (id := article["articleid"]) in params]
