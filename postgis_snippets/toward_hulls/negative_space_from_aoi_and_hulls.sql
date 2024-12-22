CREATE TABLE negativespace AS(
SELECT st_difference(a.geom, st_union(h.geom)) as geom
FROM project_aoi a, hulls h
GROUP BY a.geom);

SELECT POPULATE_GEOMETRY_COLUMNS('public.negativespace'::regclass);
CREATE INDEX negativespace_idx
ON negativespace
USING gist (geom);
