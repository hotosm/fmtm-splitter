#!/bin/python3

# Copyright (c) 2022 Humanitarian OpenStreetMap Team
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     OSM-Fieldwork is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with fmtm-splitter.  If not, see <https:#www.gnu.org/licenses/>.
#

import logging
import argparse
import sys
import os
from sys import argv
import psycopg2
from osgeo import gdal

# Instantiate logger
log = logging.getLogger(__name__)
# Splitting algorithm choices
choices = ('squares', 'file', 'custom', 'buildings')

class FMTMSplitter(object):
    """A class to split polygons"""
    def __init__(self,
                 aoi: str, # GeoJSON polygon filepath
                 algorithm: str = None,
                 ):
        self.aoi = aoi
        self.algorithm = algorithm
        if algorithm == 'squares':
            self.splitBySquare(self.size)
        elif algorithm == 'buildings':
            self.splitByBuildings

    def splitByBuildings(self,
                         aoi: str, # GeoJSON polygon input file
                         queries: list, # list of SQL queries
                         dbd: list, # database host, dbname, user, password
                         ):
        """Split the polygon by buildings in the database using an SQL query"""
        dbstring = (f"PG:host={dbd[0]} dbname={dbd[1]} "
                    f"user={dbd[2]} password={dbd[3]}")
        dbshell = psycopg2.connect(host=dbd[0], database = dbd[1],
                                   user = dbd[2], password = dbd[3])  
        dbshell.autocommit = True
        dbcursor = dbshell.cursor()
        dbcursor.execute('DROP TABLE IF EXISTS aoi;')
        # Add the AOI to the database
        log.info(f'Writing {aoi} to database as aoi layer.')
        gdal.VectorTranslate(dbstring, aoi, layerName='aoi')
        dbcursor.execute('DROP TABLE IF EXISTS project_aoi;'
                         'CREATE TABLE project_aoi AS (SELECT '
                         'ogc_fid as fid,wkb_geometry AS geom FROM aoi);'
                         'ALTER TABLE project_aoi ADD PRIMARY KEY(fid);'
                         'CREATE INDEX project_aoi_idx '
                         'ON project_aoi USING GIST (geom);'
                         'DROP TABLE aoi;')
        dbcursor.execute('VACUUM ANALYZE')
        for query in queries:
            dbcursor.execute(query)
            dbcursor.execute('VACUUM ANALYZE')
        log.info('Might very well have completed successfully')

if __name__ == "__main__":
    # Command Line options
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
        The task splitting defaults to squares, 50 meters across
        """
    )
    meters = 50
    parser.add_argument("-b", "--boundary", required=True,
                        help="Polygon AOI GeoJSON file")
    parser.add_argument("-v", "--verbose",
                        action="store_true", help="verbose output")
    parser.add_argument("-o", "--outfile",
                        default='fmtm.geojson',
                        help="Output file from splitting")
    parser.add_argument("-a", "--algorithm", default='buildings',
                        choices=choices, help="Splitting Algorithm to use")
    parser.add_argument("-m", "--meters",
                        help="Size in meters if using square splitting")
    parser.add_argument("-s", "--source",
                        help="Source data, Geojson or PG:[dbname]")
    parser.add_argument("-c", "--custom",
                        help="Custom SQL query for database]")
    parser.add_argument("-ho", "--host", help="Database host",
                        default='localhost')
    parser.add_argument("-db", "--database", help="Database to use")
    parser.add_argument("-u", "--user", help="Database username")
    parser.add_argument("-p", "--password", help="Database password")

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
    aoi = args.boundary
    splitter = FMTMSplitter(aoi)

    if args.algorithm == 'buildings':
        log.debug(f"Splitting the AOI by SQL query")
        modulardir = os.path.join(os.path.dirname(__file__),
                                  'fmtm-splitter_osm_buildings')
        modularsqlfiles = [
            "fmtm-split_01_split_AOI_by_existing_line_features.sql",
            "fmtm-split_02_count_buildings_for_subsplitting.sql",
            "fmtm-split_03_cluster_buildings.sql",
            "fmtm-split_04_create_polygons_around_clustered_buildings.sql",
            "fmtm-split_05_clean_temp_files.sql"
        ]
        modularqueries = []
        for sqlfile in modularsqlfiles:
            with open(os.path.join(modulardir, sqlfile), 'r') as sql:
                modularqueries.append(sql.read())
        dbdetails = [args.host, args.database, args.user, args.password]
        features = splitter.splitByBuildings(aoi,
                                             modularqueries,
                                             dbdetails)
        log.info(f"Wrote splitBySQL.geojson")



