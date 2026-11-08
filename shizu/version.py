# Shizu Copyright (C) 2023-2026  Ibeswipin

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__version__ = (1, 0, 5)

try:  # auto-detect from pyproject.toml with fallback
    import tomllib
    from pathlib import Path

    _pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with _pyproject.open("rb") as _f:
        _data = tomllib.load(_f)
    _ver = _data.get("project", {}).get("version", "")
    if _ver:
        __version__ = tuple(int(x) for x in _ver.split(".") if x.isdigit())
except Exception:  # pragma: no cover - keep hardcoded fallback
    pass

import os

from git import Repo

repo = Repo(os.getcwd())

branch = repo.active_branch
