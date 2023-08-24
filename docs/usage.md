# fmtm-splitter

This program splits a Polygon AOI into tasks using a varity of
algorythms.

    options:
      -h, --help            show this help message and exit
      -v, --verbose         verbose output
      -o OUTFILE, --outfile OUTFILE
          Output file from splitting
      -m METERS, --meters METERS
          Size in meters if using square splitting
      -number NUMBER, --number NUMBER
          Number of buildings in a task
      -b BOUNDARY, --boundary BOUNDARY
          Polygon AOI
      -s SOURCE, --source SOURCE
          Source data, Geojson or PG:[dbname]
      -c CUSTOM, --custom CUSTOM
          Custom SQL query for database]

The data source for existing data can be either the data extract used
by the XLSForm, or a postgresql database.

# Examples

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
