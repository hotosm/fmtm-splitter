# Copyright (c) Humanitarian OpenStreetMap Team
# This file is part of fmtm-splitter.
#
#     fmtm-splitter is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     fmtm-splitter is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with fmtm-splitter.  If not, see <https:#www.gnu.org/licenses/>.
#
"""Server config / env vars."""

import os
from dataclasses import dataclass, field


def parse_bool(value: str) -> bool:
    """Parse boolean values from environment variables."""
    return value.lower() in {"1", "true", "yes"} if value else False


@dataclass
class Settings:
    """The LiteStar application settings."""

    DEBUG: bool = field(default_factory=lambda: parse_bool(os.getenv("DEBUG", "false")))
    DB_URL: str = field(
        default_factory=lambda: os.getenv(
            "DB_URL", "postgresql://fmtm:dummycipassword@db/splitter"
        )
    )
