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
from pathlib import Path

import geojson
import psycopg2
import pytest

log = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def db():
    """Existing psycopg2 connection."""
    return psycopg2.connect("postgresql://fmtm:dummycipassword@db:5432/splitter")


@pytest.fixture(scope="session")
def aoi_json():
    """Dummy AOI GeoJSON."""
    path = Path(__file__).parent / "testdata" / "kathmandu.geojson"
    with open(path, "r") as jsonfile:
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
    with open(path, "r") as jsonfile:
        return geojson.load(jsonfile)


@pytest.fixture(scope="session")
def output_json():
    """Processed JSON using FMTM Algo on dummy AOI."""
    path = Path(__file__).parent / "testdata" / "kathmandu_processed.geojson"
    with open(path, "r") as jsonfile:
        return geojson.load(jsonfile)
