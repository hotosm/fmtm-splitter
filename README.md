# FMTM Splitter

<!-- markdownlint-disable -->
<p align="center">
  <img src="https://github.com/hotosm/fmtm/blob/main/images/hot_logo.png?raw=true" style="width: 200px;" alt="HOT"></a>
</p>
<p align="center">
  <em>A utility for splitting an AOI into multiple tasks.</em>
</p>
<p align="center">
  <a href="https://github.com/hotosm/fmtm-splitter/actions/workflows/build.yml" target="_blank">
      <img src="https://github.com/hotosm/fmtm-splitter/actions/workflows/build.yml/badge.svg" alt="Build">
  </a>
  <a href="https://github.com/hotosm/fmtm-splitter/actions/workflows/build-ci.yml" target="_blank">
      <img src="https://github.com/hotosm/fmtm-splitter/workflows/Build CI Img/badge.svg" alt="CI Build">
  </a>
  <a href="https://github.com/hotosm/fmtm-splitter/actions/workflows/docs.yml" target="_blank">
      <img src="https://github.com/hotosm/fmtm-splitter/workflows/Publish Docs/badge.svg" alt="Publish Docs">
  </a>
  <a href="https://github.com/hotosm/fmtm-splitter/actions/workflows/publish.yml" target="_blank">
      <img src="https://github.com/hotosm/fmtm-splitter/actions/workflows/publish.yml/badge.svg" alt="Publish">
  </a>
  <a href="https://github.com/hotosm/fmtm-splitter/actions/workflows/pytest.yml" target="_blank">
      <img src="https://github.com/hotosm/fmtm-splitter/workflows/PyTest/badge.svg" alt="Test">
  </a>
  <a href="https://pypi.org/project/fmtm-splitter" target="_blank">
      <img src="https://img.shields.io/pypi/v/fmtm-splitter?color=%2334D058&label=pypi%20package" alt="Package version">
  </a>
  <a href="https://pypistats.org/packages/fmtm-splitter" target="_blank">
      <img src="https://img.shields.io/pypi/dm/fmtm-splitter.svg" alt="Downloads">
  </a>
  <a href="https://github.com/hotosm/fmtm-splitter/blob/main/LICENSE.md" target="_blank">
      <img src="https://img.shields.io/github/license/hotosm/fmtm-splitter.svg" alt="License">
  </a>
</p>

---

📖 **Documentation**: <a href="https://hotosm.github.io/fmtm-splitter/" target="_blank">https://hotosm.github.io/fmtm-splitter/</a>

🖥️ **Source Code**: <a href="https://github.com/hotosm/fmtm-splitter" target="_blank">https://github.com/hotosm/fmtm-splitter</a>

---

<!-- markdownlint-enable -->

This is a program to split polygons into tasks using a variety of
algorithms. It is a class that can be used by other projects, but also
a standalone program. It was originally developed for the
[FMTM](https://github.com/hotosm/fmtm/wiki) project, but then
converted so it can be used by multiple projects.

The class takes GeoJson Polygon as an input, and returns a GeoJson
file Multipolygon of all the task boundaries.

## Installation

To install fmtm-splitter, you can use pip. Here are two options:

- Directly from the main branch:
  `pip install git+https://github.com/hotosm/fmtm-splitter.git`

- Latest on PyPi:
  `pip install fmtm-splitter`

## Splitting Types

### Split By Square

The default is to split the polygon into squares. The default
dimension is 50 meters, but that is configurable. The outer square are
clipped to the AOI boundary.

### Split By Feature

The split by feature uses highway data extracted from OpenStreetMap,
and uses it to generate non square task boundaries. It can also be
adjusted to use the number of buildings in a task to adjust it's
size.

![Split By Feature](https://github.com/hotosm/fmtm-splitter/blob/main/docs/images/Screenshot%20from%202023-08-06%2018-26-34.png)

### Custom SQL query

It is also possible to supply a custom SQL query to generate the
tasks.

## Usage In Code

- Either the FMTMSplitter class can be used directly, or the wrapper/
  helper functions can be used for splitting.

By square:

```python
import json
from fmtm_splitter.splitter import split_by_square

aoi = json.load("/path/to/file.geojson")

split_features = split_by_square(
    aoi,
    meters=100,
)
```

The FMTM splitter algorithm:

```python
import json
from fmtm_splitter.splitter import split_by_sql

aoi = json.load("/path/to/file.geojson")
osm_extracts = json.load("/path/to/file.geojson")
db = "postgresql://postgres:postgres@localhost/postgres"

split_features = split_by_sql(
    aoi,
    db,
    num_buildings=50,
    osm_extract=osm_extracts,
)
```

### Database Connections

- The db parameter can be a connection string to start a new connection.
- Or an existing database connection can be reused.
- To do this, either the psycopg2 connection, or a DBAPI connection string
  must be passed:

psycopg2 example:

```python
import psycopg2
from fmtm_splitter.splitter import split_by_sql

db = psycopg2.connect("postgresql://postgres:postgres@localhost/postgres")

split_features = split_by_sql(
    aoi,
    db,
    num_buildings=50,
    osm_extract=osm_extracts,
)
```

## Usage Via CLI

Options:

```bash
-h, --help                       show this help message and exit
-v, --verbose                    verbose output
-o OUTFILE, --outfile OUTFILE    Output file from splitting
-m METERS, --meters METERS       Size in meters if using square splitting
-b BOUNDARY, --boundary BOUNDARY Polygon AOI
-s SOURCE, --source SOURCE       Source data, Geojson or PG:[dbname]
-c CUSTOM, --custom CUSTOM       Custom SQL query for database
```

This program splits a Polygon (the Area Of Interest)
The data source for existing data can'be either the data extract
used by the XLSForm, or a postgresql database.

Examples:

```bash
fmtm-splitter -b AOI
fmtm-splitter -v -b AOI -s data.geojson
fmtm-splitter -v -b AOI -s PG:colorado

# Where AOI is the boundary of the project as a polygon
# And OUTFILE is a MultiPolygon output file,which defaults to fmtm.geojson
# The task splitting defaults to squares, 50 meters across
```

### Using the Container Image

- fmtm-splitter scripts can be used via the pre-built container images.
- These images come with all dependencies bundled, so are simple to run.
- They do however require a database, to in this case we use docker compose.

Run a specific command:

```bash
docker compose run --rm splitter fmtm-splitter <flags>
```

Run interactively (to use multiple commands):

```bash
docker compose run -it splitter bash

fmtm-splitter
```

> Note: the `output` directory in this repo is mounted in the container
> to `/data/output`. To persist data, input and output should be placed here.
