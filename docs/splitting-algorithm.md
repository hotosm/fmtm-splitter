# The AOI Splitting Algorithm

For now (as of 19-12-2024), this algorithm is entirely focused on splitting
polygon features such as buildings.

## How It Works

!!! note

 For ease of understanding, I will replace the word 'feature'
 with 'building' in the following description. But the word
 'building' could in theory be substituted by any feature type.

### 1. Split AOI By Linear Features

- First we divide up the AOI into polygons, based on the provided
  bisecting features such as roads, rivers, and railways.
- To do this we:
  - Polygonize the linear features.
  - Centroid the features to make sure they only get counted in one
    splitpolygon.
  - Clip by the AOI polygon.
- We get the database table `polygonsnocount`.
- Polygons with zero or too few features are merged into neighbours.

**Output**: Polygons covering the AOI area.

[image here]

### 2. Group Buildings By Polygon

- Next we take our buildings, insert into db table `buildings`, then find
  the polygon each building centroid is located within.
- Now we create the next table `splitpolygons` where we add the count of
  the total number of buildings within each polygon, plus the polygon
  area.

**Output**: Building dataset tagged with their containing polygon's ID.

[image here]

### 3. Cluster The Buildings

- For each polygon containing buildings, we pass through a K-Means clustering
  algorithm, to output X number of clusters.
- X is calculated as:

 ```bash
 (T / A) + 1
 T - Total building count
 A - Average number of buildings desired per cluster
 ```

!!! info

 K-Means will group buildings based on their spatial proximity, ideally
 grouping together buildings that are close together (reducing walking
 distance for mappers in the field).

- We create a table `clusteredbuildings` where we have the original buildings,
  plus their assigned cluster ID from K-Means.
  - The field `clusteruid` is a composite of `polygonid '-' clusterid`.
  - The `clusterid` is specific to the containing polygon (starting from 0).
  - For example polygon `377` will have IDs `377-0`, `377-1`, `377-2`.

!!! tip

 Using K-Means, we should be aware:

- Edge cases: sparse areas may create clusters with few buildings,
 and dense areas could result in many overlapping clusters.
- Trial and error: the clustering quality depends on fine-tuning the
 average number of buildings per cluster.

**Output**: Building dataset tagged with their containing polygon's ID,
plus a cluster ID specific to the polygon.

[image here]

### 4. Enclose The Buildings

!!! info

 We previously used a Voronoi based approach:

 1. Densify the buildings to reduce the impact of long edges
 (maximum edge 0.00004 degrees).
 2. Dump the building polygons into points.
 3. Create a Voronoi diagram (a technique to divide up the points within
 an area into polygons, where each final polygon contains the closest
 'neighbour' points from the clusters in the previous step).
 This approach had some flaws, so we have attempted other approaches, below.

- Divide up each cluster into polygons using convex hulls.
- Here we essentially form small 'islands' of buildings.
- Fixing polygon overlaps:
  - We may have a few polygon overlaps, where a building could fall between
 two polygon areas.
  - To solve this, we find all of the overlapping 'shards', and subtract
   from the polygon area.
  - We then union all de-overlapped hulls with their buildings (the
   de-overlapping will have left some feature polygons partially and
   maybe wholly outside of their home polygons, this should restore
   them without creating new overlaps unless the features themselves
   are overlapping, in which case there isn't a great solution).

**Output**: Task polygons that don't overlap and fully enclose all features,
that don't have jagged / complex edges.

[image here]

### 5. Filling The Negative Space

- Now we have our 'islands' of buildings, this would be fine if we knew
  for certain that they contained every possible building in the field.
- However, in the real world, we may have missed some buildings, so the
  task areas should be expanded out to cover the entire AOI footprint.
- We can create a 'negative' space multipolygon by subtracting the hulls
  from the AOI.
- The 'negative' space multipolygon can be filled using the
  'straight skeleton' algorithm:
  - This is essentially a Voronoi algorithm, but for polygons
   instead of points! (not exactly, but it's an analogy)
  - The algorithm will work on the edges and corners of the 'hull'
   polygons, to generate bounding 'filler' polygons between them.
    - It will perfectly bisect between buildings or polygon areas,
   instead of creating wavy / zig-zag boundaries.
- Finally, we identify the edge-sharing neighbor hull of each element
  of the polygonized skeleton, dissolve them into those neighbors.

!!! info

- Voronoi diagrams divide space based on distances to points or
 polygons, creating regions with perpendicular bisectors.
- Straight skeletons shrink polygon edges inward at equal speed
 to create a network of lines (skeleton) and subdivided polygons.
 It’s more about preserving the shape of polygons rather than
 distance-based partitioning.

**Output**: Split task area polygons.

> The original buildings, including tag data, can be superimposed on
to these task polygons, to assign them to each task area.

[image here]

### 6. Alignment Of Task Areas (Optional)

- The final problem here is aligning the polygon areas back with the
  linear features, as they may have shifted slightly during all the
  processing!
  - For example the task boundaries should ideally align in the
   center of a highway polylin.
  - Using a window function, we can essentially run the same steps
   as above, but for each specific cluster area, instead of the
   whole AOI, reducing the drift from the linear features.

**Output**: Split task area polygons, better aligned to linear features.

[image here]

## Requirements & Future Plans

Input from Ivan Gayton @ 18/12/2024

### Input Datasets

#### AOI

- Do some GeoJSON cleanup, CRS checking, and normalise to a specific format.
- Ideally we just have a Polygon GeoJSON.

#### Splitting Lines (Linear Features)

- Allow polyline input from sources other than OSM.
- From OSM:
  - Polylines: default all, but user configurable (major vs minor highways, etc).
  - Polygons: filter tags for traffic circles, water bodies, etc, then split into
    polylines.

In both cases, we likely only need the geometry, no tags.

#### Map Features

- **Points**:
  - Geometries, plus tags.
  - Centroids of polygons.
  - Midpoint of polylines.

- **Polylines**:
  - Geometries, plus tags.
  - Convert relevant polygons such as traffic circles / water bodies into
    polylines.
  - Split roads at all intersections, so that every polyline constitutes an
    edge in a graph.

- **Polygons**:
  - Geometries, plus tags.
  - Convert multipolygons (like OSM buildings with holes) into simple polygons for
  the purpose of splitting (maybe we want the multipolygons to send to the data
  collection app later, but for splitting we definitely don't want holes).
  - Do some checking/cleaning for invalid geometries.

### Output Datasets

We need the following datasets of geometries, but probably not any tags
associated:

- AOI
- Splitlines
- Features

The original features should probably be retained for later use in the
actual data collection (e.g. conflation), but for splitting purposes we
don't need all the tags and fields, and we definitely don't want any
complex geometry.

### Extra Work

Large task polygons:

- We might need to check for task polygons that are too big.
- If there are regions with sparse features, they might end
  up with giant task polygons, in which case we might want to
  sub-split them (maybe into squares).

## Testing The Workflow In QGIS

### Running Bleeding-Edge PostGIS Locally

First you may need to set up a local Postgres database, including the latest
bleeding-edge version of PostGIS and SFCGAL.

The easiest way is via Docker (single command):

 ```bash
 docker run --name aoi-splitting-db --detach \
 -p 5432:5432 -v ./db_data:/var/lib/postgresql/data/  \
 -e POSTGRES_USER=hotosm -e POSTGRES_PASSWORD=hotosm -e POSTGRES_DB=splitter \
 docker.io/postgis/postgis:17-master \
 && sleep 5 \
 && docker exec aoi-splitting-db psql -d splitter -U hotosm -c \
 'CREATE EXTENSION IF NOT EXISTS postgis_sfcgal WITH SCHEMA public;'
 ```

The instance will be available:

- Host: `localhost`
- Port: `5432`
- Database: `splitter`
- User `hotosm`
- Password `hotosm`

!!! NOTE

 Changing the port on the left side in the command `8888:5432`,
 will make Postgres available on a different port for you.

### Importing OSM Data

Get the raw-data-api Lua OSM import script:

 ```bash
 curl -LO https://raw.githubusercontent.com/hotosm/osm-rawdata/refs/heads/main/osm_rawdata/import/raw.lua
 ```

Download some data from GeoFabrik:

 <https://download.geofabrik.de>

Import into Postgres:

 ```bash
 osm2pgsql --create -H localhost -U hotosm -P 5432 -d splitter \
 -W --extra-attributes --output=flex --style ./raw.lua \
 /your-geofabrik-file.osm.pbf
 ```

### QGIS DB Manager

- Install the QGIS DB Manager plugin.
- View the geoms you just added.
- Run each step of the splitting algorithm SQL sequentially.
- View the intermediary tables and geometries created.
- More detailed instructions to come!
