#!/bin/python3

# Copyright (c) 2022 Humanitarian OpenStreetMap Team
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     FMTM-Splitter is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with FMTM-Splitter.  If not, see <https:#www.gnu.org/licenses/>.
#
"""Class and helper methods for task splitting."""

import argparse
import json
import logging
import sys
from io import BytesIO
from pathlib import Path
from textwrap import dedent
from typing import Optional, Union

import geojson
import numpy as np
from geojson import Feature, FeatureCollection, GeoJSON
from psycopg2.extensions import connection
from shapely.geometry import Polygon, shape
from shapely.ops import unary_union

from fmtm_splitter.db import aoi_to_postgis, close_connection, create_connection, create_tables, drop_tables, insert_geom
from osm_rawdata.postgres import PostgresClient

# Instantiate logger
log = logging.getLogger(__name__)


class FMTMSplitter(object):
    """A class to split polygons."""

    def __init__(
        self,
        aoi_obj: Optional[Union[str, FeatureCollection, dict]] = None,
    ):
        """This class splits a polygon into tasks using a variety of algorithms.

        Args:
            aoi_obj (str, FeatureCollection): Input AOI, either a file path,
                or GeoJSON string.

        Returns:
            instance (FMTMSplitter): An instance of this class
        """
        # Parse AOI, merge if multiple geometries
        if aoi_obj:
            geojson = self.input_to_geojson(aoi_obj)
            self.aoi = self.geojson_to_shapely_polygon(geojson)

        # Init split features
        self.split_features = None

    @staticmethod
    def input_to_geojson(input_data: Union[str, FeatureCollection, dict], merge: bool = False) -> GeoJSON:
        """Parse input data consistently to a GeoJSON obj."""
        log.info(f"Parsing GeoJSON from type {type(input_data)}")
        if isinstance(input_data, str) and len(input_data) < 250 and Path(input_data).is_file():
            # Impose restriction for path lengths <250 chars
            with open(input_data, "r") as jsonfile:
                try:
                    parsed_geojson = geojson.load(jsonfile)
                except json.decoder.JSONDecodeError as e:
                    raise IOError(f"File exists, but content is invalid JSON: {input_data}") from e

        elif isinstance(input_data, FeatureCollection):
            parsed_geojson = input_data
        elif isinstance(input_data, dict):
            parsed_geojson = geojson.loads(geojson.dumps(input_data))
        elif isinstance(input_data, str):
            geojson_truncated = input_data if len(input_data) < 250 else f"{input_data[:250]}..."
            log.debug(f"GeoJSON string passed: {geojson_truncated}")
            parsed_geojson = geojson.loads(input_data)
        else:
            err = f"The specified AOI is not valid (must be geojson or str): {input_data}"
            log.error(err)
            raise ValueError(err)

        return parsed_geojson

    @staticmethod
    def geojson_to_featcol(geojson: Union[FeatureCollection, Feature, dict]) -> FeatureCollection:
        """Standardise any geojson type to FeatureCollection."""
        # Parse and unparse geojson to extract type
        if isinstance(geojson, FeatureCollection):
            # Handle FeatureCollection nesting
            features = geojson.get("features", [])
        elif isinstance(geojson, Feature):
            # Must be a list
            features = [geojson]
        else:
            # A standard geometry type. Has coordinates, no properties
            features = [Feature(geometry=geojson)]
        return FeatureCollection(features)

    @staticmethod
    def geojson_to_shapely_polygon(geojson: Union[FeatureCollection, Feature, dict]) -> Polygon:
        """Parse GeoJSON and return shapely Polygon.

        The GeoJSON may be of type FeatureCollection, Feature, or Polygon,
        but should only contain one Polygon geometry in total.
        """
        features = FMTMSplitter.geojson_to_featcol(geojson).get("features", [])
        log.debug("Converting AOI to Shapely geometry")

        if len(features) == 0:
            msg = "The input AOI contains no geometries."
            log.error(msg)
            raise ValueError(msg)
        elif len(features) > 1:
            msg = "The input AOI cannot contain multiple geometries."
            log.error(msg)
            raise ValueError(msg)

        return shape(features[0].get("geometry"))

    def splitBySquare(  # noqa: N802
        self,
        meters: int,
    ) -> FeatureCollection:
        """Split the polygon into squares.

        Args:
            meters (int):  The size of each task square in meters.

        Returns:
            data (FeatureCollection): A multipolygon of all the task boundaries.
        """
        log.debug("Splitting the AOI by squares")

        xmin, ymin, xmax, ymax = self.aoi.bounds

        # 1 meters is this factor in degrees
        meter = 0.0000114
        length = float(meters) * meter
        width = float(meters) * meter

        cols = list(np.arange(xmin, xmax + width, width))
        rows = list(np.arange(ymin, ymax + length, length))

        polygons = []
        for x in cols[:-1]:
            for y in rows[:-1]:
                grid_polygon = Polygon([(x, y), (x + width, y), (x + width, y + length), (x, y + length)])
                clipped_polygon = grid_polygon.intersection(self.aoi)
                if not clipped_polygon.is_empty:
                    polygons.append(clipped_polygon)

        self.split_features = FeatureCollection([Feature(geometry=poly) for poly in polygons])
        return self.split_features

    def splitBySQL(  # noqa: N802
        self,
        sql: str,
        db: Union[str, connection],
        buildings: Optional[int] = None,
        osm_extract: Optional[Union[dict, FeatureCollection]] = None,
    ) -> FeatureCollection:
        """Split the polygon by features in the database using an SQL query.

        FIXME this requires some work to function with custom SQL.

        Args:
            sql (str): The SQL query to execute
            db (str, psycopg2.extensions.connection): The db url, format:
                postgresql://myusername:mypassword@myhost:5432/mydatabase
                OR an psycopg2 connection object object that is reused.
                Passing an connection object prevents requiring additional
                database connections to be spawned.
            buildings (int): The number of buildings in each task
            osm_extract (dict, FeatureCollection): an OSM extract geojson,
                containing building polygons, or linestrings.

        Returns:
            data (FeatureCollection): A multipolygon of all the task boundaries.
        """
        # Validation
        if buildings and not osm_extract:
            msg = (
                "To use the FMTM splitting algo, an OSM data extract must be passed "
                "via param `osm_extract` as a geojson dict or FeatureCollection."
            )
            log.error(msg)
            raise ValueError(msg)

        # Run custom SQL
        if not buildings or not osm_extract:
            log.info("No `buildings` or `osm_extract` params passed, executing custom SQL")
            # FIXME untested
            conn = create_connection(db)
            splitter_cursor = conn.cursor()
            log.debug("Running custom splitting algorithm")
            splitter_cursor.execute(sql)
            features = splitter_cursor.fetchall()[0][0]["features"]
            if features:
                log.info(f"Query returned {len(features)} features")
            else:
                log.info("Query returned no features")
            self.split_features = FeatureCollection(features)
            return self.split_features

        # Get existing db engine, or create new one
        conn = create_connection(db)

        # Generate db tables if not exist
        log.debug("Generating required temp tables")
        create_tables(conn)

        # Add aoi to project_aoi table
        aoi_to_postgis(conn, self.aoi)

        def json_str_to_dict(json_item: Union[str, dict]) -> dict:
            """Convert a JSON string to dict."""
            if isinstance(json_item, dict):
                return json_item
            if isinstance(json_item, str):
                try:
                    return json.loads(json_item)
                except json.JSONDecodeError:
                    msg = f"Error decoding key in GeoJSON: {json_item}"
                    log.error(msg)
                    # Set tags to empty, skip feature
                    return {}

        # Insert data extract into db, using same cursor
        log.debug("Inserting data extract into db")
        cur = conn.cursor()
        for feature in osm_extract["features"]:
            # NOTE must handle format generated from FMTMSplitter __init__
            wkb_element = shape(feature["geometry"]).wkb_hex
            properties = feature.get("properties", {})
            if "tags" in properties.keys():
                # Sometimes tags are placed under tags key
                tags = properties.get("tags", {})
            else:
                # Sometimes tags are directly in properties
                tags = properties

            # Handle nested 'tags' key if present
            tags = json_str_to_dict(tags).get("tags", json_str_to_dict(tags))
            osm_id = properties.get("osm_id")

            # Common attributes for db tables
            common_args = dict(osm_id=osm_id, geom=wkb_element, tags=tags)

            # Insert building polygons
            if tags.get("building") == "yes":
                insert_geom(cur, "ways_poly", **common_args)

            # Insert highway/waterway/railway polylines
            elif any(key in tags for key in ["highway", "waterway", "railway"]):
                insert_geom(cur, "ways_line", **common_args)

        # Use raw sql for view generation & remainder of script
        # TODO get geom from project_aoi table instead of wkb string
        log.debug("Creating db view with intersecting polylines")
        view = (
            "DROP VIEW IF EXISTS lines_view;"
            "CREATE VIEW lines_view AS SELECT "
            "tags,geom FROM ways_line WHERE "
            "ST_Intersects(ST_SetSRID(CAST(%s AS GEOMETRY), 4326), geom)"
        )
        cur.execute(view, (self.aoi.wkb_hex,))
        # Close current cursor
        cur.close()

        splitter_cursor = conn.cursor()
        log.debug("Running task splitting algorithm")
        splitter_cursor.execute(sql, {"num_buildings": buildings})

        features = splitter_cursor.fetchall()[0][0]["features"]
        if features:
            log.info(f"Query returned {len(features)} features")
        else:
            log.info("Query returned no features")

        self.split_features = FeatureCollection(features)

        # Drop tables & close (+commit) db connection
        drop_tables(conn)
        close_connection(conn)

        return self.split_features

    def splitByFeature(  # noqa: N802
        self,
        features: FeatureCollection,
    ) -> FeatureCollection:
        """Split the polygon by features in the database.

        Args:
            features(FeatureCollection): FeatureCollection of features
                to polygonise and return.

        Returns:
            data (FeatureCollection): A multipolygon of all the task boundaries.
        """
        log.debug("Polygonising the FeatureCollection features")
        # Extract all geometries from the input features
        geometries = []
        for feature in features["features"]:
            geom = feature["geometry"]
            if geom["type"] == "Polygon":
                geometries.append(shape(geom))
            elif geom["type"] == "LineString":
                geometries.append(shape(geom))
            else:
                log.warning(f"Ignoring unsupported geometry type: {geom['type']}")

        # Create a single MultiPolygon from all the polygons and linestrings
        multi_polygon = unary_union(geometries)

        # Clip the multi_polygon by the AOI boundary
        clipped_multi_polygon = multi_polygon.intersection(self.aoi)

        polygon_features = [Feature(geometry=polygon) for polygon in list(clipped_multi_polygon.geoms)]

        # Convert the Polygon Features into a FeatureCollection
        self.split_features = FeatureCollection(features=polygon_features)

        return self.split_features

    def outputGeojson(  # noqa: N802
        self,
        filename: str = "output.geojson",
    ) -> None:
        """Output a geojson file from split features."""
        if not self.split_features:
            msg = "Feature splitting has not been executed. Do this first."
            log.error(msg)
            raise RuntimeError(msg)

        with open(filename, "w") as jsonfile:
            geojson.dump(self.split_features, jsonfile)
            log.debug(f"Wrote split features to {filename}")


def split_by_square(
    aoi: Union[str, FeatureCollection],
    meters: int = 100,
    outfile: Optional[str] = None,
) -> FeatureCollection:
    """Split an AOI by square, dividing into an even grid.

    Args:
        aoi(str, FeatureCollection): Input AOI, either a file path,
            GeoJSON string, or FeatureCollection object.
        meters(str, optional): Specify the square size for the grid.
            Defaults to 100m grid.
        outfile(str): Output to a GeoJSON file on disk.

    Returns:
        features (FeatureCollection): A multipolygon of all the task boundaries.
    """
    # Parse AOI
    parsed_aoi = FMTMSplitter.input_to_geojson(aoi)
    aoi_featcol = FMTMSplitter.geojson_to_featcol(parsed_aoi)

    # Handle multiple geometries passed
    if len(feat_array := aoi_featcol.get("features", [])) > 1:
        features = []
        for index, feat in enumerate(feat_array):
            featcol = split_by_square(
                FeatureCollection(features=[feat]),
                meters,
                f"{Path(outfile).stem}_{index}.geojson)" if outfile else None,
            )
            feats = featcol.get("features", [])
            if feats:
                features += feats
        # Parse FeatCols into single FeatCol
        split_features = FeatureCollection(features)
    else:
        splitter = FMTMSplitter(aoi_featcol)
        split_features = splitter.splitBySquare(meters)
        if not split_features:
            msg = "Failed to generate split features."
            log.error(msg)
            raise ValueError(msg)
        if outfile:
            splitter.outputGeojson(outfile)

    return split_features


def split_by_sql(
    aoi: Union[str, FeatureCollection],
    db: Union[str, connection],
    sql_file: Optional[Union[str, Path]] = None,
    num_buildings: Optional[int] = None,
    outfile: Optional[str] = None,
    osm_extract: Optional[Union[str, FeatureCollection]] = None,
) -> FeatureCollection:
    """Split an AOI with a custom SQL query or default FMTM query.

    Note: either sql_file, or num_buildings must be passed.

    If sql_file is not passed, the default FMTM splitter will be used.
    The query will optimise on the following:
    - Attempt to divide the aoi into tasks that contain approximately the
        number of buildings from `num_buildings`.
    - Split the task areas on major features such as roads an rivers, to
      avoid traversal of these features across task areas.

    Also has handling for multiple geometries within FeatureCollection object.

    Args:
        aoi(str, FeatureCollection): Input AOI, either a file path,
            GeoJSON string, or FeatureCollection object.
        db (str, psycopg2.extensions.connection): The db url, format:
            postgresql://myusername:mypassword@myhost:5432/mydatabase
            OR an psycopg2 connection object that is reused.
            Passing an connection object prevents requring additional
            database connections to be spawned.
        sql_file(str): Path to custom splitting algorithm.
        num_buildings(str): The number of buildings to optimise the FMTM
            splitting algorithm with (approx buildings per generated feature).
        outfile(str): Output to a GeoJSON file on disk.
        osm_extract (str, FeatureCollection): an OSM extract geojson,
            containing building polygons, or linestrings.
            Optional param, if not included an extract is generated for you.
            It is recommended to leave this param as default, unless you know
            what you are doing.

    Returns:
        features (FeatureCollection): A multipolygon of all the task boundaries.
    """
    if not sql_file and not num_buildings:
        err = "Either sql_file or num_buildings must be passed."
        log.error(err)
        raise ValueError(err)

    # Use FMTM splitter of num_buildings set, else use custom SQL
    if not sql_file:
        sql_file = Path(__file__).parent / "fmtm_algorithm.sql"

    with open(sql_file, "r") as sql:
        query = sql.read()

    # Parse AOI
    parsed_aoi = FMTMSplitter.input_to_geojson(aoi)
    aoi_featcol = FMTMSplitter.geojson_to_featcol(parsed_aoi)

    # Extracts and parse extract geojson
    if not osm_extract:
        # We want all polylines for splitting:
        # buildings, highways, waterways, railways
        config_data = dedent(
            """
            select:
            from:
              - nodes
              - ways_poly
              - ways_line
            where:
              tags:
                - building: not null
                  highway: not null
                  waterway: not null
                  railway: not null
                  aeroway: not null
        """
        )
        # Must be a BytesIO JSON object
        config_bytes = BytesIO(config_data.encode())

        pg = PostgresClient(
            "underpass",
            config_bytes,
        )
        # The total FeatureCollection area merged by osm-rawdata automatically
        extract_geojson = pg.execQuery(
            aoi_featcol,
            extra_params={"fileName": "fmtm_splitter", "useStWithin": False},
        )

    else:
        extract_geojson = FMTMSplitter.input_to_geojson(osm_extract)

    if not extract_geojson:
        err = "A valid data extract must be provided."
        log.error(err)
        raise ValueError(err)

    # Handle multiple geometries passed
    if len(feat_array := aoi_featcol.get("features", [])) > 1:
        features = []
        for index, feat in enumerate(feat_array):
            featcol = split_by_sql(
                FeatureCollection(features=[feat]),
                db,
                sql_file,
                num_buildings,
                f"{Path(outfile).stem}_{index}.geojson)" if outfile else None,
                osm_extract,
            )
            feats = featcol.get("features", [])
            if feats:
                features += feats
        # Parse FeatCols into single FeatCol
        split_features = FeatureCollection(features)
    else:
        splitter = FMTMSplitter(aoi_featcol)
        split_features = splitter.splitBySQL(query, db, num_buildings, osm_extract=extract_geojson)
        if not split_features:
            msg = "Failed to generate split features."
            log.error(msg)
            raise ValueError(msg)
        if outfile:
            splitter.outputGeojson(outfile)

    return split_features


def split_by_features(
    aoi: Union[str, FeatureCollection],
    db_table: Optional[str] = None,
    geojson_input: Optional[Union[str, FeatureCollection]] = None,
    outfile: Optional[str] = None,
) -> FeatureCollection:
    """Split an AOI by geojson features or database features.

    Note: either db_table, or geojson_input must be passed.

    - By PG features: split by map features in a Postgres database table.
    - By GeoJSON features: split by map features from a GeoJSON file.

    Args:
        aoi(str, FeatureCollection): Input AOI, either a file path,
            GeoJSON string, or FeatureCollection object.
        geojson_input(str, FeatureCollection): Path to input GeoJSON file,
            a valid FeatureCollection, or GeoJSON string.
        db_table(str): A database table containing features to split by.
        outfile(str): Output to a GeoJSON file on disk.

    Returns:
        features (FeatureCollection): A multipolygon of all the task boundaries.

    """
    if not geojson_input and not db_table:
        err = "Either geojson_input or db_table must be passed."
        log.error(err)
        raise ValueError(err)

    # Parse AOI
    parsed_aoi = FMTMSplitter.input_to_geojson(aoi)
    aoi_featcol = FMTMSplitter.geojson_to_featcol(parsed_aoi)

    # Features from database
    if db_table:
        # data = f"PG:{db_table}"
        # TODO get input_features from db
        # input_features =
        # featcol = FMTMSplitter.geojson_to_featcol(input_features)
        raise NotImplementedError("Splitting from db featurs it not implemented yet.")

    # Features from geojson
    if geojson_input:
        input_parsed = FMTMSplitter.input_to_geojson(geojson_input)
        input_featcol = FMTMSplitter.geojson_to_featcol(input_parsed)

    if not isinstance(input_featcol, FeatureCollection):
        msg = (
            f"Could not parse geojson data from {geojson_input}"
            if geojson_input
            else f"Could not parse database data from {db_table}"
        )
        log.error(msg)
        raise ValueError(msg)

    # Handle multiple geometries passed
    if len(feat_array := aoi_featcol.get("features", [])) > 1:
        features = []
        for index, feat in enumerate(feat_array):
            featcol = split_by_features(
                FeatureCollection(features=[feat]),
                db_table,
                input_featcol,
                f"{Path(outfile).stem}_{index}.geojson)" if outfile else None,
            )
            feats = featcol.get("features", [])
            if feats:
                features += feats
        # Parse FeatCols into single FeatCol
        split_features = FeatureCollection(features)
    else:
        splitter = FMTMSplitter(aoi_featcol)
        split_features = splitter.splitByFeature(input_featcol)
        if not split_features:
            msg = "Failed to generate split features."
            log.error(msg)
            raise ValueError(msg)
        if outfile:
            splitter.outputGeojson(outfile)

    return split_features


def main(args_list: list[str] | None = None):
    """This main function lets this class be run standalone by a bash script."""
    parser = argparse.ArgumentParser(
        prog="splitter.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="This program splits a Polygon AOI into tasks",
        epilog="""
This program splits a Polygon (the Area Of Interest)

        The data source for existing data can'
be either the data extract used by the XLSForm, or a postgresql database.

    examples:
        fmtm-splitter -b AOI
        fmtm-splitter -v -b AOI -s data.geojson
        fmtm-splitter -v -b AOI -s PG:colorado

        Where AOI is the boundary of the project as a polygon
        And OUTFILE is a MultiPolygon output file,which defaults to fmtm.geojson
        The task splitting defaults to squares, 50 meters across. If -m is used
        then that also defaults to square splitting.

        fmtm-splitter -b AOI -b 20 -c custom.sql
        This will use a custom SQL query for splitting by map feature, and adjust task
        sizes based on the number of buildings.
        """,
    )
    # The default SQL query for feature splitting
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose output")
    parser.add_argument("-o", "--outfile", default="fmtm.geojson", help="Output file from splitting")
    parser.add_argument("-m", "--meters", nargs="?", const=50, help="Size in meters if using square splitting")
    parser.add_argument("-number", "--number", nargs="?", const=5, help="Number of buildings in a task")
    parser.add_argument("-b", "--boundary", required=True, help="Polygon AOI")
    parser.add_argument("-s", "--source", help="Source data, Geojson or PG:[dbname]")
    parser.add_argument("-c", "--custom", help="Custom SQL query for database")
    parser.add_argument(
        "-db", "--dburl", default="postgresql://fmtm:dummycipassword@db:5432/splitter", help="The database url string to custom sql"
    )
    parser.add_argument("-e", "--extract", help="The OSM data extract for fmtm splitter")

    # Accept command line args, or func params
    args = parser.parse_args(args_list)
    if not any(vars(args).values()):
        parser.print_help()
        return

    # Set logger
    logging.basicConfig(
        level="DEBUG" if args.verbose else "INFO",
        format=("%(asctime)s.%(msecs)03d [%(levelname)s] " "%(name)s | %(funcName)s:%(lineno)d | %(message)s"),
        datefmt="%y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    # Parse AOI file or string
    if not args.boundary:
        err = "You need to specify an AOI! (file or geojson string)"
        log.error(err)
        raise ValueError(err)

    if args.meters:
        split_by_square(
            args.boundary,
            meters=args.meters,
            outfile=args.outfile,
        )
    elif args.number:
        split_by_sql(
            args.boundary,
            db=args.dburl,
            sql_file=args.custom,
            num_buildings=args.number,
            outfile=args.outfile,
            osm_extract=args.extract,
        )
    # Split by feature using geojson
    elif args.source and args.source[3:] != "PG:":
        split_by_features(
            args.boundary,
            geojson_input=args.source,
            outfile=args.outfile,
        )
    # Split by feature using db
    elif args.source and args.source[3:] == "PG:":
        split_by_features(
            args.boundary,
            db_table=args.source[:3],
            outfile=args.outfile,
        )

    else:
        log.warning("Not enough arguments passed")
        parser.print_help()
        return


if __name__ == "__main__":
    """
    This is just a hook so this file can be run standlone during development.
    """
    main()
