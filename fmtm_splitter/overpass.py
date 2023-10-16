#!/bin/python3

import argparse
import os
import subprocess
from datetime import datetime

import requests
from osgeo import ogr


def aoiextent(aoifile):
    """Accept a GeoJSON file, return its extent as a bbox string."""
    indriver = ogr.GetDriverByName("GeoJSON")
    indata = indriver.Open(aoifile)
    inlayer = indata.GetLayer()
    e = list(inlayer.GetExtent())
    bboxstring = f"{e[2]},{e[0]},{e[3]},{e[1]}"
    return bboxstring


def query(query_string, overpass_url):
    """Accept a query in Overpass API query language,
    return an osm dataset.
    """
    try:
        response = requests.get(overpass_url, params={"data": query_string})
    except:
        print("overpass did not want to answer that one\n")
    if response.status_code == 200:
        print(f"The overpass API at {overpass_url} accepted the query and " f"returned something.")
        return response.text
    else:
        print(response)
        print("Yeah, that didn't work. We reached the Overpass API but " "something went wrong on the server side.")


def dbpush(infile, dbd):
    """Accept an osm file, push it to PostGIS layers using the Underpass schema."""
    try:
        print(f"Trying to turn {infile} into a PostGIS layer")
        style = os.path.join("fmtm_splitter", "raw.lua")
        pg = [
            "osm2pgsql",
            "--create",
            "-d",
            f"postgresql://{dbd[0]}:{dbd[1]}@{dbd[2]}:{dbd[4]}/{dbd[3]}",
            "--extra-attributes",
            "--output=flex",
            "--style",
            style,
            infile,
        ]
        print(pg)  # just to visually check that this command makes sense
        p = subprocess.run(pg, capture_output=True, encoding="utf-8")
        response = p.stdout
        error = p.stderr
        print(f"osm2pgsql seems to have accepted {infile} and " f"returned {response} \nand\n{error}")
        return response
    except Exception as e:
        print(e)


if __name__ == "__main__":
    """return a file of raw OSM data from Overpass API from an input file
    of text containing working Overpass Query Language, and push that file
    to a PostGIS database as a layer.
    """
    p = argparse.ArgumentParser(usage="usage: attachments [options]")
    p.add_argument("-q", "--query", help="Text file in overpass query language")
    p.add_argument("-b", "--boundary", help="AOI as GeoJSON file")
    p.add_argument(
        "-url", "--overpass_url", help="Overpass API server URL", default="https://overpass.kumi.systems/api/interpreter"
    )
    p.add_argument("-ho", "--host", help="Database host", default="localhost")
    p.add_argument("-db", "--database", help="Database to use")
    p.add_argument("-u", "--user", help="Database username")
    p.add_argument("-p", "--password", help="Database password")
    p.add_argument("-po", "--port", help="Database port", default="5432")

    args = p.parse_args()

    (directory, basename) = os.path.split(args.boundary)
    (basename_no_ext, extension) = os.path.splitext(basename)
    (basefilename, extension) = os.path.splitext(args.boundary)
    date = datetime.now().strftime("%Y_%m_%d")
    dirdate = os.path.join(directory, date)
    osmfilepath = f"{dirdate}_{basename_no_ext}.osm"

    q = open(args.query)
    # TODO get bbox from GeoJSON aoi
    bbox = aoiextent(args.boundary)
    qstring = q.read().replace("{{bbox}}", bbox)
    data = query(qstring, args.overpass_url)
    with open(osmfilepath, "w") as of:
        of.write(data)
        print(f"Wrote {osmfilepath}")

    dbdetails = [args.user, args.password, args.host, args.database, args.port]
    dblayers = dbpush(osmfilepath, dbdetails)
