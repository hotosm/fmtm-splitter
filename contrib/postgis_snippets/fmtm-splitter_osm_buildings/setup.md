# Setting up dev environment to test the splitter

Set up a Postgresql container with the needed dependencies and a working database with PostGIS and SFCGAL enabled.
```
docker run --name aoi-splitting-db --detach -p 6543:5432 -v ./db_data:/var/lib/postgresql/data/ -e POSTGRES_USER=hotosm -e POSTGRES_PASSWORD=hotosm -e POSTGRES_DB=splitter docker.io/postgis/postgis:17-master && sleep 5 && docker exec aoi-splitting-db psql -d splitter -U hotosm -c 'CREATE EXTENSION IF NOT EXISTS postgis_sfcgal WITH SCHEMA public;' 
```

You can use a different username and password for the db if you like.

