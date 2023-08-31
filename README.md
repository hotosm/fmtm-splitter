# fmtm-splitter

🕮 [Documentation](https://hotosm.github.io/fmtm-splitter/)

This is a program to split polygons into tasks using a variety of
algorythms. It is a class that can be used by other projects, but also
a standalone program. It was originally developed for the
[FMTM](https://github.com/hotosm/fmtm/wiki) project, but then
converted so it can be used by multiple projects.

The class takes GeoJson Polygon as an input, and returns a GeoJson
file Multipolygon of all the task boundaries.

## Split By Square

The default is to split the polygon into squares. The default
dimension is 50 meters, but that is configurable. The outer square are
clipped to the AOI boundary.

## Split By Feature

The split by feature uses highway data extracted from OpenStreetMap,
and uses it to generate non square task boundaries. It can also be
adjusted to use the number of buildings in a task to adjust it's
size.

<img align="left" width="300px" src="https://github.com/hotosm/fmtm-splitter/blob/main/docs/images/Screenshot%20from%202023-08-06%2018-26-34.png"/>

## Custom SQL query

It is also possible to supply a custom SQL query to generate the
tasks.

# The fmtm-splitter program

    options:
    -h, --help                       show this help message and exit
    -v, --verbose                    verbose output
    -o OUTFILE, --outfile OUTFILE    Output file from splitting
    -m METERS, --meters METERS       Size in meters if using square splitting
    -b BOUNDARY, --boundary BOUNDARY Polygon AOI
    -s SOURCE, --source SOURCE       Source data, Geojson or PG:[dbname]
    -c CUSTOM, --custom CUSTOM       Custom SQL query for database]

This program splits a Polygon (the Area Of Interest)
The data source for existing data can'be either the data extract used by the XLSForm, or a postgresql database.

    examples:
        fmtm-splitter -b AOI
        fmtm-splitter -v -b AOI -s data.geojson
        fmtm-splitter -v -b AOI -s PG:colorado

        Where AOI is the boundary of the project as a polygon
        And OUTFILE is a MultiPolygon output file,which defaults to fmtm.geojson
        The task splitting defaults to squares, 50 meters across
