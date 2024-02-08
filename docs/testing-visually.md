# Testing FMTM Splitter Visually

Sometimes a GeoJSON printed to the terminal just doesn't cut it...

If you wish to view the split data output in a more visual way:

## Option 1: GeoJSON.io

1. Generate a geojson bbox via [geojson.io](https://geojson.io)
2. Copy the content into `output/input.geojson` in this repo.
3. Create a data extract and place inside `output/extract.geojson`.
4. Run the splitting algorithm:

   ```bash
   docker compose run --rm splitter fmtm-splitter \
       --boundary output/input.geojson \
       --extract output/extract.geojson \
       --outfile output/output.geojson \
       --number 50
   ```

5. Copy the data from `output/output.geojson` to geojson.io to visualise.

## Option 2: FMTM
