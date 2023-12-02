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
import logging
import sys
from pathlib import Path
from sys import argv
from typing import Optional, Union

import geojson
import geopandas as gpd
import numpy as np
from geojson import FeatureCollection
from shapely.geometry import Polygon, shape
from shapely.ops import polygonize
from sqlalchemy import create_engine

# Instantiate logger
log = logging.getLogger(__name__)


class FMTMSplitter(object):
    """A class to split polygons."""

    def __init__(
        self,
        aoi: Union[str, FeatureCollection],
    ):
        """This class splits a polygon into tasks using a variety of algorithms.

        Args:
            aoi (str, FeatureCollection): Input AOI, either a file path,
                or GeoJSON string.

        Returns:
            instance (FMTMSplitter): An instance of this class
        """
        # Parse AOI
        if isinstance(aoi, str) and Path(aoi).is_file():
            log.info(f"Parsing AOI from file {aoi}")
            self.aoi = gpd.GeoDataFrame.from_file(aoi, crs="EPSG:4326")
        elif isinstance(aoi, str):
            log.info(f"Parsing AOI GeoJSON from string {aoi}")
            self.aoi = gpd.GeoDataFrame(geojson.loads(aoi), crs="EPSG:4326")
        elif isinstance(aoi, FeatureCollection):
            self.aoi = gpd.GeoDataFrame(aoi.get("features"), crs="EPSG:4326")
        else:
            err = f"The specified AOI is not valid (must be geojson or str): {aoi}"
            log.error(err)
            raise ValueError(err)

        # Rename fields to match schema & set id field
        self.id = uuid4()
        self.aoi["id"] = str(self.id)
        self.aoi.rename(columns={"geometry": "geom", "properties": "tags"}, inplace=True)
        self.aoi.drop(columns=["type"], inplace=True)
        self.aoi.set_geometry("geom", inplace=True)

        # Init split features
        self.split_features = None

    def splitBySquare(
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

        """Split the polygon by features in the database using an SQL query.

        Args:
            aoi (DataFrame): The project boundary
            sql (str): The SQL query to execute
            dburl (str): The database URI
            buildings (int): The number of buildings in each task

        Returns:
            data (FeatureCollection): A multipolygon of all the task boundaries
        """
        # Create a table with the project AOI
        con = create_engine(dburl)
        aoi.to_postgis("project_aoi", con, if_exists="replace")
        # FIXME: geopandas chokes with this SQL query as it leaves a
        # a few features without a geometry. But we like it to create the
        # table the feature splitting needs to work without modification
        # df = gpd.read_postgis(sql, con)
        # return df

        # geopandas can't handle views
        # So instead do it the manual way
        dbshell = psycopg2.connect(dburl)
        dbshell.autocommit = True
        dbcursor = dbshell.cursor()
        text = geojson.loads(aoi.to_json())
        view = f"DROP VIEW IF EXISTS lines_view;CREATE VIEW lines_view AS SELECT tags,geom FROM ways_line WHERE ST_CONTAINS(ST_GeomFromGeoJson('{text['features'][0]['geometry']}'), geom)"
        # aoi.to_postgis('lines_view', con, if_exists='replace')
        dbcursor.execute(view)

        query = sql.replace("{nbuildings}", str(buildings))
        dbcursor.execute(query)
        result = dbcursor.fetchall()
        log.info(f"Query returned {len(result[0][0]['features'])}")
        features = result[0][0]["features"]

        # clean up the temporary tables, we don't care about the result
        dbcursor.execute(
            "DROP TABLE buildings; DROP TABLE clusteredbuildings; DROP TABLE dumpedpoints; DROP TABLE lowfeaturecountpolygons; DROP TABLE voronois; DROP TABLE taskpolygons; DROP TABLE splitpolygons"
        )
        return features

    def splitByFeature(
        self,
        features: gpd.GeoDataFrame,
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

    def outputGeojson(
        self,
        filename: str = "output.geojson",
    ) -> FeatureCollection:
        """Output a geojson file from split features."""
        if not self.split_features:
            msg = "Feature splitting has not been executed. Do this first."
            log.error(msg)
            raise RuntimeError(msg)

        jsonfile = open(filename, "w")
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
    db: Union[str, Session],
    sql_file: str = None,
    num_buildings: str = None,
    osm_extract: Union[dict, FeatureCollection] = None,
    outfile: str = None,
    remove_tables: bool = True,
) -> FeatureCollection:
    """Split an AOI with a custom SQL query or default FMTM query.

    Note: either sql_file, or num_buildings must be passed.

    If sql_file is not passed, the default FMTM splitter will be used.
    The query will optimise on the following:
    - Attempt to divide the aoi into tasks that contain approximately the
        number of buildings from `num_buildings`.
    - Split the task areas on major features such as roads an rivers, to
      avoid traversal of these features across task areas.

    Args:
        aoi(str, FeatureCollection): Input AOI, either a file path,
            GeoJSON string, or FeatureCollection object.
        db(str, Session): The db url, format:
            postgresql://myusername:mypassword@myhost:5432/mydatabase
            OR an SQLAlchemy Session object that is reused.
            Passing an Session object prevents requring additional
            database sessions to be spawned.
        sql_file(str): Path to custom splitting algorithm.
        num_buildings(str): The number of buildings to optimise the FMTM
            splitting algorithm with (approx buildings per generated feature).
        osm_extract (dict, FeatureCollection): an OSM extract geojson,
            containing building polygons, or linestrings.
        outfile(str): Output to a GeoJSON file on disk.
        remove_tables (bool): Remove the generated database tables.
            Defaults to True, but may be set to False to keep the
            empty database tables after processing in complete.
            This is for a marginal performance benefit if running
            the splitting algorithm multiple times.

    Returns:
        features (FeatureCollection): A multipolygon of all the task boundaries.
    """
    splitter = FMTMSplitter(aoi)

    if not sql_file and not num_buildings:
        err = "Either sql_file or num_buildings must be passed."
        log.error(err)
        raise ValueError(err)

    # Use FMTM splitter of num_buildings set, else use custom SQL
    if num_buildings:
        sql_file = Path(__file__).parent / "fmtm_algorithm.sql"

    sql = open(sql_file, "r")
    query = sql.read()

    features = splitter.splitBySQL(query, db, num_buildings, osm_extract=osm_extract, remove_tables=remove_tables)
    if not features:
        msg = "Failed to generate split features."
        log.error(msg)
        raise ValueError(msg)

    if outfile:
        splitter.outputGeojson(outfile)

    return features


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
    splitter = FMTMSplitter(aoi)

    if not geojson_input and not db_table:
        err = "Either geojson_input or db_table must be passed."
        log.error(err)
        raise ValueError(err)

    input_features = None

    # Features from database
    if db_table:
        data = f"PG:{db_table}"
        # TODO get input_features from db
        raise NotImplementedError("Splitting from db featurs it not implemented yet.")

    # Features from geojson
    if geojson_input:
        input_features = FMTMSplitter(geojson_input).aoi

    if not isinstance(input_features, gpd.GeoDataFrame):
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


def main():
    """This main function lets this class be run standalone by a bash script."""
    parser = argparse.ArgumentParser(
        prog="FMTMSplitter.py",
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
    query = "fmtm_algorithm.sql"
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose output")
    parser.add_argument("-o", "--outfile", default="fmtm.geojson", help="Output file from splitting")
    parser.add_argument("-m", "--meters", help="Size in meters if using square splitting")
    parser.add_argument("-number", "--number", default=5, help="Number of buildings in a task")
    parser.add_argument("-b", "--boundary", required=True, help="Polygon AOI")
    parser.add_argument("-s", "--source", help="Source data, Geojson or PG:[dbname]")
    parser.add_argument("-c", "--custom", help="Custom SQL query for database")
    parser.add_argument("-db", "--dburl", help="The database url string to custom sql")

    args = parser.parse_args()
    if len(argv) < 2:
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
            inputs.boundary,
            meters=args.meters,
            outfile=args.outfile,
        )
    elif args.custom:
        split_by_sql(
            inputs.boundary,
            db=args.db,
            sql_file=custom,
            num_buildings=args.number,
            outfile=args.outfile,
        )
    # Split by feature using geojson
    elif args.source and args.source[3:] != "PG:":
        split_by_features(
            inputs.boundary,
            geojson_input=args.source,
            outfile=args.outfile,
        )
    # Split by feature using db
    elif args.source and args.source[3:] == "PG:":
        split_by_features(
            inputs.boundary,
            db_table=args.source[:3],
            outfile=args.outfile,
        )


if __name__ == "__main__":
    """
    This is just a hook so this file can be run standlone during development.
    """
    main()
