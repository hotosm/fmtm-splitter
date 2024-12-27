DROP TABLE IF EXISTS negativespacebuildings;
CREATE TABLE negativespacebuildings AS(
SELECT st_difference(a.geom, st_union(h.geom)) as geom
FROM project_aoi a, clusteredbuildings h
GROUP BY a.geom);

SELECT POPULATE_GEOMETRY_COLUMNS('public.negativespacebuildings'::regclass);
CREATE INDEX negativespacebuildings_idx
ON negativespacebuildings
USING gist (geom);
