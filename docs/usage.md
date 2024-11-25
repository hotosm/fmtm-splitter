# fmtm-splitter

This program splits a Polygon AOI into tasks using a varity of
algorithms.

```bash
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
          Custom SQL query for database
      -db DATABASE, --dburl DATABASE
          The database url string to custom sql
```

The data source for existing data can be either the data extract used
by the XLSForm, or a postgresql database.

## Examples

### Via Command Line

```bash
fmtm-splitter -b AOI --meters 50
fmtm-splitter -v -b AOI -s data.geojson
fmtm-splitter -v -b AOI -s PG:colorado
```

> Where AOI is the boundary of the project as a polygon
> And OUTFILE is a MultiPolygon output file,which defaults to fmtm.geojson
> The task splitting defaults to squares, 50 meters across. If -m is used
> then that also defaults to square splitting.

#### With Custom Query

```bash
fmtm-splitter -b AOI -c custom.sql
```

> This will use a custom SQL query for splitting by map feature, and adjust task
> sizes based on the number of buildings.

#### Using FMTM Splitting Algorithm

```bash
fmtm-splitter -b "/path/to/aoi.geojson" \
    -db "postgresql://myuser:mypass@myhost:5432/mydb" \
    -number 10 -e "/path/to/extract.geojson"
```

### Via API

#### Split By Square

```python
from fmtm_splitter.splitter import split_by_square

features = split_by_square(
    "path/to/your/file.geojson",
    meters=100,
)
```

#### Split By Features

```python
import geojson
from fmtm_splitter.splitter import split_by_features

aoi_json = geojson.load("/path/to/file.geojson")
# Dump string to show that passing string json is possible too
split_geom_json = geojson.dumps(geojson.load("/path/to/file.geojson"))

features = split_by_features(
    aoi_json,
    split_geom_json,
)
```

#### Split By SQL

```python
import geojson
from fmtm_splitter.splitter import split_by_sql

aoi_json = geojson.load("/path/to/file.geojson")
extract_json = geojson.load("/path/to/file.geojson")

features = split_by_sql(
    aoi_json,
    "postgresql://myuser:mypass@myhost:5432/mydb",
    num_buildings=10,
    osm_extract=extract_json,
)
```
