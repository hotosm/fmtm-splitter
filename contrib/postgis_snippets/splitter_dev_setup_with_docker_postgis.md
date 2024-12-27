# Setting up dev environment to test the splitter

Set up a Postgresql container with the needed dependencies and a working database with PostGIS and SFCGAL enabled.
```
docker run --name aoi-splitting-db --detach -p 6543:5432 -v ./db_data:/var/lib/postgresql/data/ -e POSTGRES_USER=hotosm -e POSTGRES_PASSWORD=hotosm -e POSTGRES_DB=splitter docker.io/postgis/postgis:17-master && sleep 5 && docker exec aoi-splitting-db psql -d splitter -U hotosm -c 'CREATE EXTENSION IF NOT EXISTS postgis_sfcgal WITH SCHEMA public;' 
```

You can use a different username and password (in lieu of hotosm and hotosm) for the db if you like.

This will retain data between restarts, but the Docker container with the database in it won't start between reboots. After rebooting your computer, you can restart this container with ```docker start aoi-splitting-db``` and the database will become available on port 6543. 

# Load some OSM data into the PostGIS db

- Use HOT Raw Data API or grab an area from the [Geofabrik download server](https://download.geofabrik.de/) to get a .pbf file. Put it in a local directory.
- Grab [the raw.lua file from the HOT Raw Data API Git repo](https://github.com/hotosm/raw-data-api/blob/develop/backend/raw.lua). Put it in a local directory.
- If you don't have it already, install osm2pgsql (on Debian/Ubuntu, ```sudo apt install osm2pgsql```).
- Run osm2pgsql to import OSM data into the database. The raw.lua file specifies the way in which the database columns are organized, most critically ensuring that the OSM tags are in a jsonb column called "tags," which allows the splitting algorithm to correctly query the tags.```osm2pgsql -H localhost -U hotosm -P 6543 -d splitter -W --extra-attributes --output=flex --style PATH/TO/raw.lua PATH/TO/my_OSM_data.pbf``` (you'll probably have to input the db password) **TODO** ad the db password to this command

# Connect to the PostGIS db in QGIS

# NOTES
When trying to skeletonize from the negative space created by subtracting the buildings from the AOI, I get:
```
SQL error: WITH ns AS (   select * from "negativespacebuildings" )  ,spinalsystem AS(   select CG_StraightSkeleton(ns.geom) as geom   from ns )  select * from spinalsystem returned 0 [ERROR:  straight skeleton of Polygon with point touching rings is not implemented. Error at POINT (-4211389437820263/35184372088832 3490600832540767/70368744177664)]
```