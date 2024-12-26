select c1.fid as fid1, c2.fid as fid2, st_intersection(c1.geom,c2.geom) as geom
from hulls as c1, hulls as c2
where c1.fid > c2.fid and st_intersects(c1.geom,c2.geom)