# Testing FMTM Splitter Visually

Sometimes a GeoJSON printed to the terminal just doesn't cut it...

If you wish to view the split data output in a more visual way:

## Option 1: GeoJSON.io

1. Generate a geojson bbox via [geojson.io](https://geojson.io)
2. Copy the content into `output/input.geojson` in this repo.
3. Run the splitting algorithm:

   ```bash
   docker compose run --rm splitter fmtm-splitter \
       --boundary output/input.geojson \
       --outfile output/output.geojson \
       --number 50
   ```

4. Copy the data from `output/output.geojson` to geojson.io to visualise.

## Option 2: FMTM

1. Setup FMTM:

   ```bash
   git clone https://github.com/hotosm/fmtm.git
   cd fmtm
   cp .env.example .env

   # Open docker-compose.yml and uncomment
   - ../osm-rawdata/osm_rawdata:/home/appuser/.local/lib/python3.10/site-packages/osm_rawdata

   # Run FMTM
   docker compose up -d
   ```

2. Go to the [FMTM dashboard](http://fmtm.localhost:7050/)
3. Create a new project.
4. Upload your project AOI.
5. Upload or generate a data extract.
6. On the task splitting page, select `Task Splitting Algorithm`.
7. Then click `Click to generate tasks` to see the algorithm output.
