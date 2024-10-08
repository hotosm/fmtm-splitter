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

import json
import logging
from pathlib import Path
from time import sleep
from uuid import uuid4

import geojson
import pytest

from fmtm_splitter.splitter import (
    FMTMSplitter,
    main,
    split_by_features,
    split_by_sql,
    split_by_square,
)

log = logging.getLogger(__name__)


def test_init_splitter_types(aoi_json):
    """Test parsing different types with FMTMSplitter."""
    # FeatureCollection
    FMTMSplitter(aoi_json)
    # GeoJSON String
    geojson_str = geojson.dumps(aoi_json)
    FMTMSplitter(geojson_str)
    # GeoJSON File
    FMTMSplitter("tests/testdata/kathmandu.geojson")
    # GeoJSON Dict FeatureCollection
    geojson_dict = dict(aoi_json)
    FMTMSplitter(geojson_dict)
    # GeoJSON Dict Feature
    feature = geojson_dict.get("features")[0]
    FMTMSplitter(feature)
    # GeoJSON Dict Polygon
    polygon = feature.get("geometry")
    FMTMSplitter(polygon)
    # FeatureCollection multiple geoms (4 polygons)
    with pytest.raises(ValueError) as error:
        FMTMSplitter("tests/testdata/kathmandu_split.geojson")
    assert str(error.value) == "The input AOI cannot contain multiple geometries."


def test_split_by_square_with_dict(aoi_json, extract_json):
    """Test divide by square from geojson dict types."""
    features = split_by_square(
        aoi_json.get("features")[0], meters=50, osm_extract=extract_json
    )
    assert len(features.get("features")) == 50
    features = split_by_square(
        aoi_json.get("features")[0].get("geometry"), meters=50, osm_extract=extract_json
    )
    assert len(features.get("features")) == 50


def test_split_by_square_with_str(aoi_json, extract_json):
    """Test divide by square from geojson str and file."""
    # GeoJSON Dumps
    features = split_by_square(
        geojson.dumps(aoi_json.get("features")[0]), meters=50, osm_extract=extract_json
    )
    assert len(features.get("features")) == 50
    # JSON Dumps
    features = split_by_square(
        json.dumps(aoi_json.get("features")[0].get("geometry")),
        meters=50,
        osm_extract=extract_json,
    )
    assert len(features.get("features")) == 50
    # File
    features = split_by_square(
        "tests/testdata/kathmandu.geojson",
        meters=100,
        osm_extract="tests/testdata/kathmandu_extract.geojson",
    )
    assert len(features.get("features")) == 15


def test_split_by_square_with_file_output():
    """Test divide by square from geojson file.

    Also write output to file.
    """
    outfile = Path(__file__).parent.parent / f"{uuid4()}.geojson"
    features = split_by_square(
        "tests/testdata/kathmandu.geojson",
        osm_extract="tests/testdata/kathmandu_extract.geojson",
        meters=50,
        outfile=str(outfile),
    )
    assert len(features.get("features")) == 50
    # Also check output file
    with open(outfile, "r") as jsonfile:
        output_geojson = geojson.load(jsonfile)
    assert len(output_geojson.get("features")) == 50


def test_split_by_square_with_multigeom_input(aoi_multi_json, extract_json):
    """Test divide by square from geojson dict types."""
    file_name = uuid4()
    outfile = Path(__file__).parent.parent / f"{file_name}.geojson"
    features = split_by_square(
        aoi_multi_json,
        meters=50,
        osm_extract=extract_json,
        outfile=str(outfile),
    )
    assert len(features.get("features", [])) == 50
    for index in [0, 1, 2, 3]:
        assert Path(f"{Path(outfile).stem}_{index}.geojson)").exists()


def test_split_by_features_geojson(aoi_json):
    """Test divide by square from geojson file.

    kathmandu_split.json contains 4 polygons inside the kathmandu.json area.
    """
    features = split_by_features(
        aoi_json,
        geojson_input="tests/testdata/kathmandu_split.geojson",
    )
    assert len(features.get("features")) == 4


def test_split_by_sql_fmtm_with_extract(db, aoi_json, extract_json, output_json):
    """Test divide by square from geojson file."""
    features = split_by_sql(
        aoi_json,
        db,
        num_buildings=5,
        osm_extract=extract_json,
    )
    assert len(features.get("features")) == 120
    assert sorted(features) == sorted(output_json)


def test_split_by_sql_fmtm_no_extract(aoi_json):
    """Test FMTM splitting algorithm, with no data extract."""
    features = split_by_sql(
        aoi_json,
        # Use separate db connection for longer running test
        "postgresql://fmtm:dummycipassword@db:5432/splitter",
        num_buildings=5,
    )
    # This may change over time as it calls the live API
    assert len(features.get("features")) > 120


def test_split_by_sql_fmtm_multi_geom(extract_json):
    """Test divide by square from geojson file with multiple geometries."""
    with open("tests/testdata/kathmandu_split.geojson", "r") as jsonfile:
        parsed_featcol = geojson.load(jsonfile)
    features = split_by_sql(
        parsed_featcol,
        "postgresql://fmtm:dummycipassword@db:5432/splitter",
        num_buildings=10,
        osm_extract=extract_json,
    )

    assert isinstance(features, geojson.feature.FeatureCollection)
    assert isinstance(features.get("features"), list)
    assert isinstance(features.get("features")[0], dict)
    assert len(features.get("features")) == 35

    polygons = [
        feature
        for feature in features.get("features", [])
        if feature.get("geometry").get("type") == "Polygon"
    ]
    assert len(polygons) == 35

    polygon_feat = geojson.loads(json.dumps(polygons[0]))
    assert isinstance(polygon_feat, geojson.Feature)

    polygon = geojson.loads(json.dumps(polygons[0].get("geometry")))
    assert isinstance(polygon, geojson.geometry.Polygon)


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
    extract_geojson = Path(__file__).parent / "testdata" / "kathmandu_extract.geojson"
    outfile = Path(__file__).parent.parent / f"{uuid4()}.geojson"

    try:
        main(
            [
                "--boundary",
                str(infile),
                "--meters",
                "100",
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

    assert len(output_geojson.get("features")) == 15


def test_split_by_features_cli():
    """Test split by features works via CLI."""
    infile = Path(__file__).parent / "testdata" / "kathmandu.geojson"
    outfile = Path(__file__).parent.parent / f"{uuid4()}.geojson"
    split_geojson = Path(__file__).parent / "testdata" / "kathmandu_split.geojson"
    extract_geojson = Path(__file__).parent / "testdata" / "kathmandu_extract.geojson"

    try:
        main(
            [
                "--boundary",
                str(infile),
                "--source",
                str(split_geojson),
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

    assert len(output_geojson.get("features")) == 60


def test_split_by_sql_cli_no_extract():
    """Test split by sql works via CLI."""
    # Sleep 3 seconds before test to ease raw-data-api
    sleep(3)
    infile = Path(__file__).parent / "testdata" / "kathmandu.geojson"
    outfile = Path(__file__).parent.parent / f"{uuid4()}.geojson"

    try:
        main(
            [
                "--boundary",
                str(infile),
                "--dburl",
                "postgresql://fmtm:dummycipassword@db:5432/splitter",
                "--number",
                "10",
                "--outfile",
                str(outfile),
            ]
        )
    except SystemExit:
        pass

    with open(outfile, "r") as geojson_out:
        output_geojson = geojson.load(geojson_out)

    # This may change over time as it uses the live API
    assert len(output_geojson.get("features")) > 60
