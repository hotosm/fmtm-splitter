# Copyright (c) 2022, 2023 Humanitarian OpenStreetMap Team
#
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
"""Configuration and fixtures for PyTest."""

import logging

# from typing import Any, Generator
from pathlib import Path

import geojson
import pytest

# from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionmaker
# from sqlalchemy_utils import create_database, database_exists

# engine = create_engine(settings.FMTM_DB_URL.unicode_string())
# TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Base.metadata.create_all(bind=engine)

log = logging.getLogger(__name__)


def pytest_configure(config):
    """Configure pytest runs."""
    # Stop sqlalchemy logs
    sqlalchemy_log = logging.getLogger("sqlalchemy")
    sqlalchemy_log.propagate = False


@pytest.fixture(scope="session")
def aoi_json():
    """Dummy AOI GeoJSON."""
    path = Path(__file__).parent / "testdata" / "kathmandu.geojson"
    jsonfile = open(path, "r")
    return geojson.load(jsonfile)


@pytest.fixture(scope="session")
def extract_json():
    """Dummy data extract GeoJSON."""
    # # Get the extract geojson
    # import requests
    # import json
    # query = {
    #     "filters": {
    #         "tags": {
    #             "all_geometry": {
    #                 "join_or": {"building": [], "highway": [], "waterway": []}
    #             }
    #         }
    #     }
    # }
    # path = Path(__file__).parent / "testdata" / "kathmandu.geojson"
    # jsonfile = open(path, "r")
    # json_boundary = geojson.load(jsonfile)
    # query["geometry"] = json_boundary.get("features", None)[0].get("geometry")
    # query["fileName"] = "extract"
    # query["outputType"] = "geojson"
    # print(query)
    # query_url = f"https://api-prod.raw-data.hotosm.org/v1/snapshot/"
    # headers = {"accept": "application/json", "Content-Type": "application/json"}
    # result = requests.post(query_url, data=json.dumps(query), headers=headers)
    # print(result.status_code)
    # print(result)
    # task_id = result.json()["task_id"]
    # print(task_id)
    path = Path(__file__).parent / "testdata" / "kathmandu_extract.geojson"
    jsonfile = open(path, "r")
    return geojson.load(jsonfile)


# @pytest.fixture(scope="session")
# def db_engine():
#     """The SQLAlchemy database engine to init."""
#     engine = create_engine(settings.FMTM_DB_URL.unicode_string())
#     if not database_exists:
#         create_database(engine.url)

#     Base.metadata.create_all(bind=engine)
#     yield engine


# @pytest.fixture(scope="function")
# def db(db_engine):
#     """Database session using db_engine."""
#     connection = db_engine.connect()

#     # begin a non-ORM transaction
#     connection.begin()

#     # bind an individual Session to the connection
#     db = TestingSessionLocal(bind=connection)

#     yield db

#     db.rollback()
#     connection.close()
