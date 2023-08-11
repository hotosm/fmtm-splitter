#!/bin/python3

import sys, os
import argparse
import requests
from datetime import datetime
from osgeo import gdal
import subprocess

def query(query_string, overpass_url):
    """Accept a query in Overpass API query language,
       return an osm dataset.
    """
    try:
        response = requests.get(overpass_url,
                                params={'data': query_string})
    except:
        print("overpass did not want to answer that one\n")
    if response.status_code == 200:
        print(f'The overpass API at {overpass_url} accepted the query and '\
              f'returned something.')
        return response.text
    else:
        print(response)
        print("Yeah, that didn't work. We reached the Overpass API but "\
              "something went wrong on the server side.")

def osm2pgsql(infile, dbd):
    """

    """
    try:
        print(f'Trying to turn {infile} into a PostGIS layer')
        #osm2pgsql --create -H localhost -U user -P 5432 -d dbname -W --extra-attributes --output=flex --style raw.lua infile.osm' 
        p = subprocess.run(["osm2pgsql", infile],
                           capture_output=True, encoding='utf-8')
        response = p.stdout
        print(f'osm2pgsql seems to have accepted {infile} and '\
              f'returned something of type {type(response)}')
        return response
    except Exception as e:
        print(e)

if __name__ == "__main__":
    """return a file of raw OSM data from Overpass API from an input file
    of text containing working Overpass Query Language, and push that file
    to a PostGIS database as a layer.
    """
    p = argparse.ArgumentParser(usage="usage: attachments [options]")
    p.add_argument('-q', '--query', help="Text file in overpass query language")
    p.add_argument('-b', '--boundary', help="AOI as GeoJSON file")
    p.add_argument('-url', '--overpass_url', help='Overpass API server URL',
                   default="https://overpass.kumi.systems/api/interpreter")
    p.add_argument("-ho", "--host", help="Database host",
                        default='localhost')
    p.add_argument("-db", "--database", help="Database to use")
    p.add_argument("-u", "--user", help="Database username")
    p.add_argument("-p", "--password", help="Database password")

    args = p.parse_args()

    (directory, basename) = os.path.split(args.boundary)
    (basename_no_ext, extension) = os.path.splitext(basename)
    (basefilename, extension) = os.path.splitext(args.boundary)
    date = datetime.now().strftime("%Y_%m_%d")
    dirdate = os.path.join(directory, date)
    osmfilepath = f'{dirdate}_{basename_no_ext}.osm'
    
    q = open(args.query)
    aoi = open(args.boundary)
    # TODO get bbox from GeoJSON aoi
    bbox = '27.726144,85.323000,27.733567,85.331926'
    qstring = q.read().replace('{{bbox}}', bbox)
    print(qstring)
    data = query(qstring, args.overpass_url)
    with open(osmfilepath, 'w') as of:
        of.write(data)
        print(f'Wrote {osmfilepath}')
    
    dbdetails = [args.host, args.database, args.user, args.password]
    dbpush = osm2pgsql(osmfilepath, dbdetails)
