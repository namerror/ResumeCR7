from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping


APP_DATA_DIR_NAME = "ResumeCR7"
LINUX_APP_DATA_DIR_NAME = "resumecr7"


def resolve_default_data_dir(
    *,
    repo_root: Path,
    packaged: bool,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    if not packaged:
        return repo_root / "user"

    current_platform = platform if platform is not None else sys.platform
    current_environ = environ if environ is not None else os.environ
    home_dir = home if home is not None else Path.home()

    if current_platform == "darwin":
        return home_dir / "Library" / "Application Support" / APP_DATA_DIR_NAME

    if current_platform.startswith("win"):
        local_app_data = current_environ.get("LOCALAPPDATA") or current_environ.get(
            "APPDATA"
        )
        if local_app_data:
            return Path(local_app_data) / APP_DATA_DIR_NAME
        return home_dir / "AppData" / "Local" / APP_DATA_DIR_NAME

    xdg_data_home = current_environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / LINUX_APP_DATA_DIR_NAME
    return home_dir / ".local" / "share" / LINUX_APP_DATA_DIR_NAME
