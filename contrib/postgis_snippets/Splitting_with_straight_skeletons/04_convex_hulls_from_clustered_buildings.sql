-- Create table hulls: convex hulls from clustered buildings
DROP TABLE IF EXISTS hulls;
CREATE TABLE hulls AS (
  --select st_concavehull(st_collect(clb.geom),0.8) as geom, 
  SELECT clb.polyid, clb.cid, clb.clusteruid, st_convexhull(st_collect(clb.geom)) as geom
  FROM clusteredbuildings clb
  GROUP BY clb.clusteruid, clb.cid, clb.polyid
);

ALTER TABLE hulls ADD COlUMN fid SERIAL;
  
SELECT POPULATE_GEOMETRY_COLUMNS('public.hulls'::regclass);
CREATE INDEX hulls_idx
ON hulls
USING gist (geom);