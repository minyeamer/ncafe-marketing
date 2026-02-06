from __future__ import annotations

from task.farm import Farmer, MaxRetries, QuiteHours
from extensions.gsheets import WorksheetConnection
from extensions.vpn import VpnConfig
from utils.common import Delay

from typing import TypedDict, TYPE_CHECKING
import os
import yaml

if TYPE_CHECKING:
    from pathlib import Path


CONFIGS = [
    ".secrets/config.yaml",
    ".secrets/설정.yaml",
    "config.yaml",
    "설정.yaml",
]

class BrowserConfig(TypedDict, total=False):
    device: str
    mobile: bool
    headless: bool
    action_delay: Delay
    goto_delay: Delay
    reload_delay: Delay
    upload_delay: Delay

class ReadConfig(TypedDict):
    configs: WorksheetConnection
    openai_key: str | Path
    quiet_hours: QuiteHours
    comment_threshold: float
    like_threshold: float

class RunConfig(TypedDict, total=False):
    max_retries: MaxRetries
    num_my_articles: int
    max_read_length: int
    reload_start_step: int
    wait_until_read: bool
    task_delay: float
    vpn_delay: float
    with_state: bool
    verbose: int | str | Path
    dry_run: bool
    save_log: bool


def read_configs(config_path: str | Path | None = None) -> dict:
    files = [str(config_path)] + CONFIGS if config_path else CONFIGS
    for file_path in files:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding="utf-8") as file:
                return yaml.safe_load(file.read())


def main(
        browser: BrowserConfig,
        read: ReadConfig,
        run: RunConfig,
        vpn: VpnConfig,
        write: WorksheetConnection,
    ):
    farmer = Farmer(**browser, **read, vpn_config=vpn, write_config=write)
    farmer.start(**run)


if __name__ == "__main__":
    main(**read_configs())
