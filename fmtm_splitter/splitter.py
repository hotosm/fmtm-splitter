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

import argparse
import logging
import sys
from sys import argv

import geojson
import geopandas as gpd
import numpy as np
import psycopg2
from geojson import FeatureCollection, Polygon, dump
from shapely.geometry import Polygon
from shapely.ops import polygonize
from sqlalchemy import create_engine

# Instantiate logger
log = logging.getLogger(__name__)
# Splitting algorythm choices
choices = ("squares", "file", "custom")

class FMTMSplitter(object):
    """A class to split polygons."""
    def __init__(self,
                 boundary: gpd.GeoDataFrame,
                 algorythm: str = None,
                 ):
        """This class splits a polygon into tasks using a variety of algorythms.

        Args:
            boundary (FeatureCollection): The boundary polygon
            algorythm (str): The splitting algorythm to use

        Returns:
            instance (FMTMSplitter): An instance of this class
        """
        self.size = 50          # 50 meters
        self.boundary = boundary
        self.algorythm = algorythm
        if algorythm == "squares":
            self.splitBySquare(self.size)
        elif algorythm == "osm":
            pass
        elif algorythm == "custom":
            pass

    def splitBySquare(self,
                      meters: int,
                      ):
        """Split the polygon into squares.

        Args:
            meters (int):  The size of each task square in meters

        Returns:
            data (FeatureCollection): A multipolygon of all the task boundaries
        """
        gdf = gpd.GeoDataFrame.from_features(self.boundary)

        xmin, ymin, xmax, ymax = gdf.total_bounds

        # 1 meters is this factor in degrees
        meter = 0.0000114
        length = float(meters) * meter
        wide = float(meters) * meter

        cols = list(np.arange(xmin, xmax + wide, wide))
        rows = list(np.arange(ymin, ymax + length, length))

        polygons = []
        for x in cols[:-1]:
            for y in rows[:-1]:
                polygons.append(Polygon([(x,y), (x+wide, y), (x+wide, y+length), (x, y+length)]))

                grid = gpd.GeoDataFrame({"geometry":polygons})
        clipped = gpd.clip(grid, gdf)
        data = geojson.loads(clipped.to_json())
        return data

    def splitBySQL(self,
                   aoi: gpd.GeoDataFrame,
                   sql: str,
                   dburl: dict,
                   buildings: int
                   ):
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
        dbcursor.execute("DROP TABLE buildings; DROP TABLE clusteredbuildings; DROP TABLE dumpedpoints; DROP TABLE lowfeaturecountpolygons; DROP TABLE voronois; DROP TABLE taskpolygons; DROP TABLE splitpolygons")
        return features

    def splitByFeature(self,
                       aoi: gpd.GeoDataFrame,
                       features: gpd.GeoDataFrame,
                       ):
        """Split the polygon by features in the database."""
        # gdf[(gdf['highway'] != 'turning_circle') | (gdf['highway'] != 'milestone')]
        # gdf[(gdf.geom_type != 'Point')]
        # gdf[['highway']]
        gdf = gpd.GeoDataFrame.from_features(features)
        polygons = gpd.GeoSeries(polygonize(gdf.geometry))
        return polygons

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
        """
    )
    # the size of each task wheh using square splitting
    # the number of buildings in a task when using feature splitting
    buildings = 5
    # The default SQL query for feature splitting
    query = "fmtm_algorithm.sql"
    parser.add_argument("-v", "--verbose",  action="store_true", help="verbose output")
    parser.add_argument("-o", "--outfile", default="fmtm.geojson", help="Output file from splitting")
    # parser.add_argument("-a", "--algorythm", default='squares', choices=choices, help="Splitting Algorthm to use")
    parser.add_argument("-m", "--meters", help="Size in meters if using square splitting")
    parser.add_argument("-number", "--number", default=buildings, help="Number of buildings in a task")
    parser.add_argument("-b", "--boundary", required=True, help="Polygon AOI")
    parser.add_argument("-s", "--source", help="Source data, Geojson or PG:[dbname]")
    parser.add_argument("-c", "--custom", help="Custom SQL query for database]")

    args = parser.parse_args()
    if len(argv) < 2:
        parser.print_help()
        quit()

    # if verbose, dump to the terminal.
    formatter = logging.Formatter(
        "%(threadName)10s - %(name)s - %(levelname)s - %(message)s"
    )
    level = logging.DEBUG
    if args.verbose:
        log.setLevel(level)
    else:
        log.setLevel(logging.INFO)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(formatter)
    log.addHandler(ch)

    # log.debug("debug")
    # log.info("info")
    # log.info("warning")

    # Read in the project AOI, which needs to be a GeoJson file
    aoi = gpd.GeoDataFrame.from_file(args.boundary)
    splitter = FMTMSplitter(aoi)

    if args.meters:
        # split the AOI into squares
        log.debug("Splitting the AOI by squares")
        tasks = splitter.splitBySquare(args.meters)
        jsonfile = open(args.outfile, "w")
        dump(tasks, jsonfile)
        log.debug(f"Wrote {args.outfile}")
    elif args.custom:
        # split the AOI using features from an SQL query
        log.debug("Splitting the AOI by SQL query")
        sqlfile = "fmtm_algorithm.sql"
        sqlfile = open(args.custom, "r")
        query = sqlfile.read()
        # dburl = "postgresql://myusername:mypassword@myhost:5432/mydatabase"
        dburl = "postgresql://localhost:5432/colorado"
        features = splitter.splitBySQL(aoi, query, dburl, args.number)
        # features.to_file('splitBySQL.geojson', driver='GeoJSON')
        collection = FeatureCollection(features)
        out = open("splitBySQL.geojson", "w")
        geojson.dump(collection, out)
        log.info("Wrote splitBySQL.geojson")
    elif args.source and args.source[3:] != "PG:":
        log.debug("Splitting the AOI using a data extract")
        # split the AOI using features in a data file
        indata = gpd.GeoDataFrame.from_file(args.source)
        # indata.query('highway', inplace=True)
        features = splitter.splitByFeature(aoi, indata)
        features.to_file("splitByFeature.geojson", driver="GeoJSON")
        log.info("Wrote splitByFeature.geojson")

        # log.info(f"Wrote {args.outfile}")

if __name__ == "__main__":
    """This is just a hook so this file can be run standlone during development."""
    main()

