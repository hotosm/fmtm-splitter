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
from pathlib import Path
from typing import Optional, Union
from uuid import uuid4

import geojson

# TODO refactor out geopandas
import geopandas as gpd
import numpy as np
from geojson import Feature, FeatureCollection
from psycopg2.extensions import connection
from shapely.geometry import Polygon, shape
from shapely.ops import polygonize

from fmtm_splitter.db import close_connection, create_connection, create_tables, drop_tables, gdf_to_postgis, insert_geom

# Instantiate logger
log = logging.getLogger(__name__)


class FMTMSplitter(object):
    """A class to split polygons."""

    def __init__(
        self,
        aoi_obj: Union[str, FeatureCollection],
    ):
        """This class splits a polygon into tasks using a variety of algorithms.

        Args:
            aoi_obj (str, FeatureCollection): Input AOI, either a file path,
                or GeoJSON string.

        Returns:
            instance (FMTMSplitter): An instance of this class
        """
        # Parse AOI
        log.info(f"Parsing GeoJSON from type {type(aoi_obj)}")
        if isinstance(aoi_obj, str) and len(aoi_obj) < 250 and Path(aoi_obj).is_file():
            # Impose restriction for path lengths <250 chars
            with open(aoi_obj, "r") as jsonfile:
                geojson_dict = geojson.load(jsonfile)
            self.aoi = self.parse_geojson(geojson_dict)
        elif isinstance(aoi_obj, FeatureCollection):
            self.aoi = self.parse_geojson(aoi_obj)
        elif isinstance(aoi_obj, dict):
            geojson_dict = geojson.loads(geojson.dumps(aoi_obj))
            self.aoi = self.parse_geojson(geojson_dict)
        elif isinstance(aoi_obj, str):
            geojson_truncated = aoi_obj if len(aoi_obj) < 250 else f"{aoi_obj[:250]}..."
            log.debug(f"GeoJSON string passed: {geojson_truncated}")
            geojson_dict = geojson.loads(aoi_obj)
            self.aoi = self.parse_geojson(geojson_dict)
        else:
            err = f"The specified AOI is not valid (must be geojson or str): {aoi_obj}"
            log.error(err)
            raise ValueError(err)

        # Rename fields to match schema & set id field
        self.id = uuid4()
        self.aoi["id"] = str(self.id)

        # Init split features
        self.split_features = None

    @staticmethod
    def parse_geojson(geojson: Union[FeatureCollection, Feature, dict]) -> gpd.GeoDataFrame:
        """Parse GeoJSON and return GeoDataFrame.

        The GeoJSON may be of type FeatureCollection, Feature, or Geometry.
        """
        # Parse and unparse geojson to extract type
        if isinstance(geojson, FeatureCollection):
            # Handle FeatureCollection nesting
            features = geojson.get("features")
        elif isinstance(geojson, Feature):
            # GeoPandas requests list of features
            features = [geojson]
        else:
            # A standard geometry type. Has coordinates, no properties
            features = [Feature(geometry=geojson)]

        log.debug(f"Parsed {len(features)} features")
        log.debug("Converting to geodataframe")
        data = gpd.GeoDataFrame(features, crs="EPSG:4326")
        return FMTMSplitter.tidy_columns(data)

    @staticmethod
    def tidy_columns(dataframe: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Fix dataframe columns prior to geojson export or db insert.

        Strips timestamps that are not json serializable.
        Renames geometry column --> geom.
        Removes 'type' field for insert into db.
        """
        log.debug("Tidying up columns, renaming geometry to geom")
        dataframe.rename(columns={"geometry": "geom", "properties": "tags"}, inplace=True)
        dataframe.set_geometry("geom", inplace=True)
        dataframe.drop(columns=["type"], inplace=True, errors="ignore")
        # Drop any timestamps to prevent json parsing issues later
        dataframe.drop(columns=["timestamp"], inplace=True, errors="ignore")
        return dataframe

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

        xmin, ymin, xmax, ymax = self.aoi.total_bounds

        # 1 meters is this factor in degrees
        meter = 0.0000114
        length = float(meters) * meter
        wide = float(meters) * meter

        cols = list(np.arange(xmin, xmax + wide, wide))
        rows = list(np.arange(ymin, ymax + length, length))

        polygons = []
        for x in cols[:-1]:
            for y in rows[:-1]:
                polygons.append(Polygon([(x, y), (x + wide, y), (x + wide, y + length), (x, y + length)]))
                grid = gpd.GeoDataFrame({"geometry": polygons}, crs="EPSG:4326")

        clipped = gpd.clip(grid, self.aoi)
        self.split_features = geojson.loads(clipped.to_json())
        return self.split_features

    def splitBySQL(  # noqa: N802
        self,
        sql: str,
        db: Union[str, connection],
        buildings: int,
        osm_extract: Union[dict, FeatureCollection] = None,
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

        # Get existing db engine, or create new one
        conn = create_connection(db)

        # Generate db tables if not exist
        log.debug("Generating required temp tables")
        create_tables(conn)

        # Add aoi to project_aoi table
        log.debug(f"Adding AOI to project_aoi table: {self.aoi.to_dict()}")
        self.aoi["tags"] = self.aoi["tags"].apply(json.dumps)
        gdf_to_postgis(self.aoi, conn, "project_aoi", "geom")

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
            tags = properties.get("tags", {})

            # Handle nested 'tags' key if present
            tags = json_str_to_dict(tags.get("tags", tags))
            osm_id = properties.get("osm_id")

            # Common attributes for db tables
            common_args = dict(project_id=self.id, osm_id=osm_id, geom=wkb_element, tags=tags)

            # Insert building polygons
            if tags.get("building") == "yes":
                insert_geom(cur, "ways_poly", **common_args)

            # Insert highway/waterway/railway polylines
            elif any(key in tags for key in ["highway", "waterway", "railway"]):
                insert_geom(cur, "ways_line", **common_args)

        # Use raw sql for view generation & remainder of script
        log.debug("Creating db view with intersecting highways")
        # Get aoi as geojson
        aoi_geom = geojson.loads(self.aoi.to_json())["features"][0]["geometry"]
        view = (
            "DROP VIEW IF EXISTS lines_view;"
            "CREATE VIEW lines_view AS SELECT "
            "tags,geom FROM ways_line WHERE "
            "ST_CONTAINS(ST_GeomFromGeoJson(%(geojson_str)s), geom)"
        )
        cur.execute(view, {"geojson_str": aoi_geom})
        # Close current cursor
        cur.close()

        splitter_cursor = conn.cursor()
        # Only insert buildings param is specified
        log.debug("Running task splitting algorithm")
        if buildings:
            splitter_cursor.execute(sql, {"num_buildings": buildings})
        else:
            splitter_cursor.execute(sql)

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
            features(gpd.GeoSeries): GeoDataFrame of feautures to split by.

        Returns:
            data (FeatureCollection): A multipolygon of all the task boundaries.
        """
        # gdf[(gdf['highway'] != 'turning_circle') | (gdf['highway'] != 'milestone')]
        # gdf[(gdf.geom_type != 'Point')]
        # gdf[['highway']]
        log.debug("Splitting the AOI using a data extract")
        gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
        polygons = gpd.GeoSeries(polygonize(gdf.geometry))

        self.split_features = geojson.loads(polygons.to_json())
        return self.split_features

    def outputGeojson(  # noqa: N802
        self,
        filename: str = "output.geojson",
    ) -> FeatureCollection:
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
    outfile: str = None,
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
    splitter = FMTMSplitter(aoi)
    features = splitter.splitBySquare(meters)
    if not features:
        msg = "Failed to generate split features."
        log.error(msg)
        raise ValueError(msg)

    if outfile:
        splitter.outputGeojson(outfile)

    return features


def split_by_sql(
    aoi: Union[str, FeatureCollection],
    db: Union[str, connection],
    sql_file: str = None,
    num_buildings: int = None,
    osm_extract: Union[str, FeatureCollection] = None,
    outfile: str = None,
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
        osm_extract (str, FeatureCollection): an OSM extract geojson,
            containing building polygons, or linestrings.
        outfile(str): Output to a GeoJSON file on disk.

    Returns:
        features (FeatureCollection): A multipolygon of all the task boundaries.
    """
    if not sql_file and not num_buildings:
        err = "Either sql_file or num_buildings must be passed."
        log.error(err)
        raise ValueError(err)

    # Use FMTM splitter of num_buildings set, else use custom SQL
    if num_buildings:
        sql_file = Path(__file__).parent / "fmtm_algorithm.sql"

    with open(sql_file, "r") as sql:
        query = sql.read()

    extract_geojson = None
    # Extracts and parse extract geojson
    if osm_extract:
        extract_geojson = geojson.loads(FMTMSplitter(osm_extract).aoi.to_json())
    if not extract_geojson:
        err = "A valid data extract must be provided."
        log.error(err)
        raise ValueError(err)

    # Handle multiple geometries passed
    if isinstance(aoi, FeatureCollection):
        # FIXME why does only one geom split during test?
        # FIXME other geoms return None during splitting
        if len(feat_array := aoi.get("features", [])) > 1:
            split_geoms = []
            for feat in feat_array:
                splitter = FMTMSplitter(feat)
                featcol = splitter.splitBySQL(query, db, num_buildings, osm_extract=extract_geojson)
                features = featcol.get("features", [])
                if features:
                    split_geoms += features
            if not split_geoms:
                msg = "Failed to generate split features."
                log.error(msg)
                raise ValueError(msg)
            if outfile:
                with open(outfile, "w") as jsonfile:
                    geojson.dump(split_geoms, jsonfile)
                    log.debug(f"Wrote split features to {outfile}")
            # Parse FeatCols into single FeatCol
            return FeatureCollection(split_geoms)

    splitter = FMTMSplitter(aoi)
    split_geoms = splitter.splitBySQL(query, db, num_buildings, osm_extract=extract_geojson)
    if not split_geoms:
        msg = "Failed to generate split features."
        log.error(msg)
        raise ValueError(msg)
    if outfile:
        splitter.outputGeojson(outfile)

    return split_geoms


def split_by_features(
    aoi: Union[str, FeatureCollection],
    db_table: str = None,
    geojson_input: Optional[Union[str, FeatureCollection]] = None,
    outfile: str = None,
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

    splitter = FMTMSplitter(aoi)
    input_features = None

    # Features from database
    if db_table:
        # data = f"PG:{db_table}"
        # TODO get input_features from db
        raise NotImplementedError("Splitting from db featurs it not implemented yet.")

    # Features from geojson
    if geojson_input:
        input_features = geojson.loads(FMTMSplitter(geojson_input).aoi.to_json())

    if not isinstance(input_features, FeatureCollection):
        msg = (
            f"Could not parse geojson data from {geojson_input}"
            if geojson_input
            else f"Could not parse database data from {db_table}"
        )
        log.error(msg)
        raise ValueError(msg)

    features = splitter.splitByFeature(input_features)
    if not features:
        msg = "Failed to generate split features."
        log.error(msg)
        raise ValueError(msg)

    if outfile:
        splitter.outputGeojson(outfile)

    return features


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
    parser.add_argument("-db", "--dburl", help="The database url string to custom sql")
    parser.add_argument("-e", "--extract", help="The OSM data extract for fmtm splitter")

    # Accept command line args, or func params
    args = parser.parse_args(args_list)
    if not any(vars(args).values()):
        parser.print_help()
        quit()

    # Parse AOI file or string
    if not args.boundary:
        err = "You need to specify an AOI! (file or geojson string)"
        log.error(err)
        raise ValueError(err)

    # if verbose, dump to the terminal.
    formatter = logging.Formatter("%(threadName)10s - %(name)s - %(levelname)s - %(message)s")
    level = logging.DEBUG
    if args.verbose:
        log.setLevel(level)
    else:
        log.setLevel(logging.INFO)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(formatter)
    log.addHandler(ch)

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
            osm_extract=args.extract,
            outfile=args.outfile,
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


if __name__ == "__main__":
    """
    This is just a hook so this file can be run standlone during development.
    """
    main()
