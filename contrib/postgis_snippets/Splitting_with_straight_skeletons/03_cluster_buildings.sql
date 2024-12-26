DROP TABLE IF EXISTS clusteredbuildings;
CREATE TABLE clusteredbuildings AS (
    WITH splitpolygonswithcontents AS (
        SELECT *
        FROM splitpolygons AS sp
        WHERE sp.numfeatures > 0
    ),

    -- Add the count of features in the splitpolygon each building belongs to
    -- to the buildings table; sets us up to be able to run the clustering.
    buildingswithcount AS (
        SELECT
            b.*,
            p.numfeatures
        FROM buildings AS b
        LEFT JOIN splitpolygons AS p
            ON b.polyid = p.polyid
    ),

    buildingstocluster AS (
        SELECT * FROM buildingswithcount AS bc
        WHERE bc.numfeatures > 0
    ),

    clusteredbuildingsnocombineduid AS (
        SELECT
            *,
            ST_CLUSTERKMEANS(
                b.geom,
                CAST((b.numfeatures / 17) + 1 AS integer)
            )
                OVER (PARTITION BY b.polyid)
            AS cid
        FROM buildingstocluster AS b
    ),

    -- uid combining the id of the outer splitpolygon and inner cluster
    clusteredbuildings AS (
        SELECT
            *,
            polyid::text || '-' || cid AS clusteruid
        FROM clusteredbuildingsnocombineduid
    )

    SELECT * FROM clusteredbuildings
);
-- ALTER TABLE clusteredbuildings ADD PRIMARY KEY(osm_id);
SELECT POPULATE_GEOMETRY_COLUMNS('public.clusteredbuildings'::regclass);
CREATE INDEX clusteredbuildings_idx
ON clusteredbuildings
USING gist (geom);
