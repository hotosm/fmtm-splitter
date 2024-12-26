DROP TABLE IF EXISTS polygonsnocount;
-- Create table polygonsnocount: a polygon layer of splits by lines
-- TODO: figure out how to allow users to decide which lines should be used
-- to split. For example, sometimes we might want to use residential roads,
-- other times not (a mapper would probably not want to cross a busy trunk road
-- unless necessary, whereas the most efficient way to visit every buildings
-- on a quiet residential road is to walk along the street and visit all of the
-- buildings on both sides!
-- TODO: Include (and convert to polylines) polygon features such as traffic
-- circles.

DO $$
    DECLARE 
    lines_count INTEGER;
BEGIN
    -- Check if ways_line has any data
    SELECT COUNT(*) INTO lines_count
    FROM "ways_line" l
    WHERE (
        (l.tags->>'highway' IS NOT NULL 
		AND 
        l.tags->>'highway' NOT IN (
		--'unclassified', 
		--'residential', 
		'service', '
		pedestrian', 
		'track', 
		'bus_guideway'
		))
        OR l.tags->>'waterway' IS NOT NULL
        OR l.tags->>'railway' IS NOT NULL
    );
    IF lines_count > 0 THEN
    CREATE TABLE polygonsnocount AS (
        -- The Area of Interest provided by the person creating the project
        WITH aoi AS (
            SELECT * FROM "project_aoi"
        )
        , splitlines AS (
            SELECT ST_Intersection(a.geom, l.geom) AS geom
            FROM aoi a
            JOIN "ways_line" l ON ST_Intersects(a.geom, l.geom)
            WHERE (
                (l.tags->>'highway' IS NOT NULL AND 
                l.tags->>'highway' NOT IN (
				  --'unclassified', 
				  --'residential', 
				  'service', 
				  'pedestrian', 
				  'track', 
				  'bus_guideway'))
                OR l.tags->>'waterway' IS NOT NULL
                OR l.tags->>'railway' IS NOT NULL
            )
        )
            
        -- Merge all lines, necessary so that the polygonize function works later
        ,merged AS (
            SELECT ST_LineMerge(ST_Union(splitlines.geom)) AS geom
            FROM splitlines
        )
        -- Combine the boundary of the AOI with the splitlines
        -- First extract the Area of Interest boundary as a line
        ,boundary AS (
            SELECT ST_Boundary(geom) AS geom
            FROM aoi
        )
        -- Then combine it with the splitlines
        ,comb AS (
            SELECT ST_Union(boundary.geom, merged.geom) AS geom
            FROM boundary, merged
        )
        -- TODO add closed ways from OSM to lines (roundabouts etc)
        -- Create a polygon for each area enclosed by the splitlines
        ,splitpolysnoindex AS (
            SELECT (ST_Dump(ST_Polygonize(comb.geom))).geom as geom
            FROM comb
        )
        -- Add an index column to the split polygons
        ,splitpolygons AS(
            SELECT
            row_number () over () as polyid,
                ST_Transform(spni.geom,4326)::geography AS geog,
            spni.* 
            from splitpolysnoindex spni
        )
        SELECT * FROM splitpolygons
    );
    ELSE
        -- Calculate number of buildings per cluster
        CREATE TABLE polygonsnocount AS (
            WITH aoi AS (
                SELECT * FROM "project_aoi"
            )
            ,transformed_aoi AS(
                SELECT
                row_number () over () as polyid,
                ST_Transform(aoi.geom,4326)::geography AS geog,
                aoi.geom 
                from aoi
            )
            SELECT * FROM transformed_aoi
        );
    END IF;
END $$;

-- Make that index column a primary key
ALTER TABLE polygonsnocount ADD PRIMARY KEY (polyid);
-- Properly register geometry column (makes QGIS happy)
SELECT POPULATE_GEOMETRY_COLUMNS('public.polygonsnocount'::regclass);
-- Add a spatial index (vastly improves performance for a lot of operations)
CREATE INDEX polygonsnocount_idx
ON polygonsnocount
USING gist (geom);
-- Clean up the table which may have gaps and stuff from spatial indexing
-- VACUUM ANALYZE polygonsnocount;