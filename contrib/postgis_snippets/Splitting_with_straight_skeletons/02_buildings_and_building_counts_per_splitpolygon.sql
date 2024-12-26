-- Create tables
--   buildings: polygon layer of buildings from OSM ways_poly
--   splitpolygons: polygon layer from polygonsnocount with building
--   count field
DROP TABLE IF EXISTS buildings;
CREATE TABLE buildings AS (
    SELECT
        b.*,
        polys.polyid
    FROM ways_poly AS b, polygonsnocount AS polys
    WHERE
        ST_INTERSECTS(polys.geom, ST_CENTROID(b.geom))
        AND b.tags ->> 'building' IS NOT NULL
);


-- ALTER TABLE buildings ADD PRIMARY KEY(osm_id);


-- Properly register geometry column (makes QGIS happy)
SELECT POPULATE_GEOMETRY_COLUMNS('public.buildings'::regclass);
-- Add a spatial index (vastly improves performance for a lot of operations)
CREATE INDEX buildings_idx
ON buildings
USING gist (geom);
-- Clean up the table which may have gaps and stuff from spatial indexing
-- VACUUM ANALYZE buildings;

DROP TABLE IF EXISTS splitpolygons;
CREATE TABLE splitpolygons AS (
    WITH polygonsfeaturecount AS (
        SELECT
            sp.polyid,
            sp.geom,
            sp.geog,
            COUNT(b.geom) AS numfeatures,
            ST_AREA(sp.geog) AS area
        FROM polygonsnocount AS sp
        LEFT JOIN buildings AS b
            ON sp.polyid = b.polyid
        GROUP BY sp.polyid, sp.geom
    )

    SELECT * FROM polygonsfeaturecount
);
ALTER TABLE splitpolygons ADD PRIMARY KEY (polyid);
SELECT POPULATE_GEOMETRY_COLUMNS('public.splitpolygons'::regclass);
CREATE INDEX splitpolygons_idx
ON splitpolygons
USING gist (geom);
-- VACUUM ANALYZE splitpolygons;