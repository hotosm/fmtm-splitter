#!/bin/python3

import sys, os
import argparse
import requests
import json
import subprocess
from datetime import datetime

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
        data = response.json()
        return data
    else:
        print(response)
        print("Yeah, that didn't work. We reached the Overpass API but "\
              "something went wrong on the server side.")

if __name__ == "__main__":
    """return a file of raw OSM data from Overpass API from an input file
    of text containing working Overpass Query Language
    """
    p = argparse.ArgumentParser(usage="usage: attachments [options]")
    p.add_argument('infile', help = "Text file in overpass query language")
    p.add_argument('-url', '--overpass_url', help='Overpass API server URL',
                   default="https://overpass.kumi.systems/api/interpreter")
    args = p.parse_args()

    (directory, basename) = os.path.split(args.infile)
    (basename_no_ext, extension) = os.path.splitext(basename)
    (basefilename, extension) = os.path.splitext(args.infile)
    date = datetime.now().strftime("%Y_%m_%d")
    dirdate = os.path.join(directory, date)
    outpath = f'{dirdate}_{basename_no_ext}.osm'
    
    with open(args.infile) as inf:
        data = query(inf.read(), args.overpass_url)
    
        with open(outfilepath, 'w') as of:
            of.write(data)
