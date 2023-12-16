# CHANGELOG

## 0.2.5 (2023-12-16)

### Fix

- improve handling of tags as json str
- return error on empty or invalid data extract

## 0.2.4 (2023-12-07)

### Fix

- run drop_all for tables prior to create_all (if exist)
- split_by_sql if no data extract provided

## 0.2.3 (2023-12-06)

### Fix

- handle multiple geoms if within FeatureCollection
- correctly handle file context for outputGeojson
- fix parsing of Feature type, improve logging
- prevent attempting to parse paths >250 chars (i.e. geojson)

## 0.2.2 (2023-12-05)

### Fix

- pass geojson as features, not geopandas df
- manage aoi parsing: geom, feat, featcol
- correct parsing of dict aoi objects

### Refactor

- reduce verbosity of logging when parsing geojsons
- merge dict and str aoi parsing

## 0.2.1 (2023-12-05)

### Refactor

- add comment to remove geopandas

## 0.2.0 (2023-12-04)

### Feat

- split by sql use osm_extracts and init db tables
- add helper functions for each split type
- add outputGeojson method

### Fix

- fix passing osm_extract via cmd line + api
- handle case where tags key is nested
- drop timestamp field is parsed in geojson
- sql splitting, commit transactions
- fix parsing of osm tags for db insert
- use gpd.read_file over GeoDataFrame.from_file
- add osm_id to ways_lines + ways_poly
- correctly pass args.dburl on cmd line
- correct extract highways into ways_lines
- drop of geojson type field if not exists
- use same session for all db queries
- refactor FMTMSplitter init to set aoi
- add db models to repo for generating tables
- update project_aoi geometry field --> geom

### Refactor

- command line to use helper functions
- split by feature
- split by square

## 0.1.0 (2023-10-25)

### Fix

- Add Doxygen and pvreverse support
- Add mkdocs config file
- Add mkdocs commentss to all classes and methods
- Add mkdocstrings-python to dependencies
- Ad dminimal doc support for mkdocs
- Add initial doc for the fmtm-splitter client
- Add workflow to update the wiki, probably won't work yet
- Supply the number of buildings per task at runtime
- Make the number of buildings parameter configurable at runtime
- Add something to the README.md doc
- Add screenshot of task splitting by feature
- standalone class & script to genersate tasks within an AOI
- Add support to be installed by pip
- Add basic documentation files

### Refactor

- rename LICENSE.md --> LICENSE
- rename build-ci workflow build_ci
- remove refs to wiki
