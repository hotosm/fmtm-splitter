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
from pathlib import Path
from uuid import uuid4

import geojson

from fmtm_splitter.splitter import main, split_by_features, split_by_sql, split_by_square

log = logging.getLogger(__name__)


def test_split_by_square_with_str(aoi_json):
    """Test divide by square from geojson obj."""
    features = split_by_square(
        geojson.dumps(aoi_json.get("features")),
        meters=50,
    )
    assert len(features.get("features")) == 54
    features = split_by_square(
        "tests/testdata/kathmandu.geojson",
        meters=100,
    )
    assert len(features.get("features")) == 15


def test_split_by_square_with_obj(aoi_json):
    """Test divide by square from geojson obj."""
    features = split_by_square(
        aoi_json,
        meters=50,
    )
    assert len(features.get("features")) == 54
    features = split_by_square(
        "tests/testdata/kathmandu.geojson",
        meters=100,
    )
    assert len(features.get("features")) == 15


def test_split_by_square_with_files():
    """Test divide by square from geojson file.

    Also write output to file.
    """
    outfile = Path(__file__).parent.parent / f"{uuid4()}.geojson"
    features = split_by_square(
        "tests/testdata/kathmandu.geojson",
        meters=50,
        outfile=str(outfile),
    )
    assert len(features.get("features")) == 54
    # Also check output file
    with open(outfile, "r") as jsonfile:
        output_geojson = geojson.load(jsonfile)
    assert len(output_geojson.get("features")) == 54


def test_split_by_features_geojson(aoi_json):
    """Test divide by square from geojson file.

    kathmandu_split.json contains 4 polygons inside the kathmandu.json area.
    """
    features = split_by_features(
        aoi_json,
        geojson_input="tests/testdata/kathmandu_split.geojson",
    )
    assert len(features.get("features")) == 4


def test_split_by_sql_fmtm(aoi_json, extract_json, output_json):
    """Test divide by square from geojson file."""
    features = split_by_sql(
        aoi_json,
        "postgresql://fmtm:dummycipassword@db:5432/splitter",
        num_buildings=5,
        osm_extract=extract_json,
    )
    assert len(features.get("features")) == 122
    assert sorted(features) == sorted(output_json)


def test_cli_help(capsys):
    """Check help text displays on CLI."""
    try:
        main(["--help"])
    except SystemExit:
        pass
    captured = capsys.readouterr().out
    assert "This program splits a Polygon AOI into tasks" in captured


def test_split_by_square_cli():
    """Test split by square works via CLI."""
    infile = Path(__file__).parent / "testdata" / "kathmandu.geojson"
    outfile = Path(__file__).parent.parent / f"{uuid4()}.geojson"

    try:
        main(["--boundary", str(infile), "--meters", "100", "--outfile", str(outfile)])
    except SystemExit:
        pass

    with open(outfile, "r") as jsonfile:
        output_geojson = geojson.load(jsonfile)

    assert len(output_geojson.get("features")) == 15


def test_split_by_features_cli():
    """Test split by features works via CLI."""
    infile = Path(__file__).parent / "testdata" / "kathmandu.geojson"
    outfile = Path(__file__).parent.parent / f"{uuid4()}.geojson"
    split_geojson = Path(__file__).parent / "testdata" / "kathmandu_split.geojson"

    try:
        main(["--boundary", str(infile), "--source", str(split_geojson), "--outfile", str(outfile)])
    except SystemExit:
        pass

    with open(outfile, "r") as jsonfile:
        output_geojson = geojson.load(jsonfile)

    assert len(output_geojson.get("features")) == 4


def test_split_by_sql_cli():
    """Test split by sql works via CLI."""
    infile = Path(__file__).parent / "testdata" / "kathmandu.geojson"
    outfile = Path(__file__).parent.parent / f"{uuid4()}.geojson"
    extract_geojson = Path(__file__).parent / "testdata" / "kathmandu_extract.geojson"

    try:
        main(
            [
                "--boundary",
                str(infile),
                "--dburl",
                "postgresql://fmtm:dummycipassword@db:5432/splitter",
                "--number",
                "10",
                "--extract",
                str(extract_geojson),
                "--outfile",
                str(outfile),
            ]
        )
    except SystemExit:
        pass

    with open(outfile, "r") as jsonfile:
        output_geojson = geojson.load(jsonfile)

    assert len(output_geojson.get("features")) == 62
