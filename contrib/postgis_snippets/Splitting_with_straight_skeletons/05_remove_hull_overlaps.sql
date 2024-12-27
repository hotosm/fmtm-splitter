DROP TABLE IF EXISTS trimmedhulls;
CREATE TABLE trimmedhulls AS (
  SELECT 
    fid, polyid, cid, clusteruid, 
	COALESCE(
      ST_Difference(
        geom,
		  (SELECT ST_Union(b.geom) 
          FROM hulls b
          WHERE 
	        (ST_Intersects(a.geom, b.geom)
            AND a.fid != b.fid)
	      )
	  ),
	  a.geom
    )
AS geom
FROM hulls a
);

ALTER TABLE trimmedhulls ADD PRIMARY KEY (fid);
SELECT POPULATE_GEOMETRY_COLUMNS('public.trimmedhulls'::regclass);
CREATE INDEX trimmedhulls_idx
ON trimmedhulls
USING gist (geom);