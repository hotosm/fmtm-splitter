# Copyright (c) 2022, 2023 Humanitarian OpenStreetMap Team
#
# This file is part of fmtm-splitter.
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with fmtm-splitter.  If not, see <https:#www.gnu.org/licenses/>.
#
"""Test task splitting algorithms."""

import logging

import geojson

from fmtm_splitter.splitter import split_by_features, split_by_sql, split_by_square

log = logging.getLogger(__name__)


def test_divide_by_square_with_str(aoi_json):
    """Test divide by square from geojson obj."""
    features = split_by_square(
        geojson.dumps(aoi_json.get("features")),
        meters=50,
    )
    assert len(features.get("features")) == 24
    features = split_by_square(
        "tests/testdata/annecy.geojson",
        meters=100,
    )
    assert len(features.get("features")) == 6


def test_divide_by_square_with_obj(aoi_json):
    """Test divide by square from geojson obj."""
    features = split_by_square(
        aoi_json,
        meters=50,
    )
    assert len(features.get("features")) == 24
    features = split_by_square(
        "tests/testdata/annecy.geojson",
        meters=100,
    )
    assert len(features.get("features")) == 6


def test_divide_by_square_with_files():
    """Test divide by square from geojson file.

    Also write output to file.
    """
    features = split_by_square(
        "tests/testdata/annecy.geojson",
        meters=50,
        outfile="output.geojson",
    )
    assert len(features.get("features")) == 24
    features = split_by_square(
        "tests/testdata/annecy.geojson",
        meters=100,
    )
    assert len(features.get("features")) == 6


def test_split_by_features_geojson(aoi_json):
    """Test divide by square from geojson file.

    annecy_split.json contains 4 polygons inside the annecy.json area.
    """
    features = split_by_features(
        aoi_json,
        geojson_input="tests/testdata/annecy_split.geojson",
    )
    assert len(features.get("features")) == 4


def test_split_by_sql_fmtm(aoi_json, extract_json):
    """Test divide by square from geojson file."""
    features = split_by_sql(
        aoi_json,
        "postgresql://fmtm:dummycipassword@db:5432/splitter",
        num_buildings=5,
        osm_extract=extract_json,
    )
    print(features)
    # TODO fix me once features returned


# TODO add test for custom sql split
