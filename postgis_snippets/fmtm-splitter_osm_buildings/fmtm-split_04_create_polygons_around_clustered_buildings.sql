/*
Licence: GPLv3 <https://www.gnu.org/licenses/gpl-3.0.html>
Part of the HOT Field Mapping Tasking Manager (FMTM)

Inputs:

Outputs:
- Point layer dumpedpoints (building perimeters chopped into small segments and all nodes converted to points)
- Polygon layer voronoids (Voronoi polygons from the building segment points, only geometry without attributes because PostGIS is annoying on that score)
- Polygon layer voronois (the Voronoi polygons from the previous layer, re-associated with the ID of the points they were created from)
- Polygon layer unsimplifiedtaskpolygons (polygons mostly enclosing each task, made by dissolving the voronois by clusteruid)
- Polygon layer taskpolygons (the polygons from above simplified to make them less jagged, easier to display, and smaller memory footprint)

*/

/*
***************************PARAMETERS FOR ROB**********************
- Line 28: Segment length to chop up the building perimeters. Currently 0.00001 degrees (about a meter near the equator). When there are buildings very close together, this value needs to be small to reduce task polygons poking into buildings from neighboring tasks. When buildings are well-spaced, this value can be bigger to save on performance overhead.
- Line 101: Simplification tolerance. Currently 0.000075 (about 7.5 meters near the equator). The larger this value, the more smoothing of Voronoi jaggies happens, but the more likely task perimeters are to intersect buildings from neighboring tasks.
*/

--*****************Densify dumped building nodes******************
DROP TABLE IF EXISTS dumpedpoints;
CREATE TABLE dumpedpoints AS (
    SELECT
        cb.osm_id,
        cb.polyid,
        cb.cid,
        cb.clusteruid,
        -- POSSIBLE BUG: PostGIS' Voronoi implementation sometimes panics
        -- with segments less than 0.00004 degrees.
        (st_dumppoints(st_segmentize(cb.geom, 0.00001))).geom
    FROM clusteredbuildings AS cb
);
SELECT populate_geometry_columns('public.dumpedpoints'::regclass);
CREATE INDEX dumpedpoints_idx
ON dumpedpoints
USING gist (geom);

--VACUUM ANALYZE dumpedpoints;

--*******************voronoia****************************************
DROP TABLE IF EXISTS voronoids;
CREATE TABLE voronoids AS (
    SELECT
        st_intersection((st_dump(st_voronoipolygons(
            st_collect(points.geom)
        ))).geom,
        sp.geom) AS geom
    FROM dumpedpoints AS points,
        splitpolygons AS sp
    WHERE st_contains(sp.geom, points.geom)
    GROUP BY sp.geom
);
CREATE INDEX voronoids_idx
ON voronoids
USING gist (geom);

--VACUUM ANALYZE voronoids;


DROP TABLE IF EXISTS voronois;
CREATE TABLE voronois AS (
    SELECT
        p.clusteruid,
        v.geom
    FROM voronoids AS v, dumpedpoints AS p
    WHERE st_within(p.geom, v.geom)
);
CREATE INDEX voronois_idx
ON voronois
USING gist (geom);

--VACUUM ANALYZE voronois;


DROP TABLE IF EXISTS unsimplifiedtaskpolygons;
CREATE TABLE unsimplifiedtaskpolygons AS (
    SELECT
        clusteruid,
        st_union(geom) AS geom
    FROM voronois
    GROUP BY clusteruid
);
CREATE INDEX unsimplifiedtaskpolygons_idx
ON unsimplifiedtaskpolygons
USING gist (geom);

--VACUUM ANALYZE unsimplifiedtaskpolygons;


--*****************************Simplify*******************************
-- Extract unique line segments
DROP TABLE IF EXISTS taskpolygons;
CREATE TABLE taskpolygons AS (
    --Convert task polygon boundaries to linestrings
    WITH rawlines AS (
        SELECT
            utp.clusteruid,
            st_boundary(utp.geom) AS geom
        FROM unsimplifiedtaskpolygons AS utp
    ),

    -- Union, which eliminates duplicates from adjacent polygon boundaries
    unionlines AS (
        SELECT st_union(l.geom) AS geom FROM rawlines AS l
    ),

    -- Dump, which gives unique segments.
    segments AS (
        SELECT (st_dump(l.geom)).geom AS geom
        FROM unionlines AS l
    ),

    agglomerated AS (
        SELECT st_linemerge(st_unaryunion(st_collect(s.geom))) AS geom
        FROM segments AS s
    ),

    simplifiedlines AS (
        SELECT st_simplify(a.geom, 0.000075) AS geom
        FROM agglomerated AS a
    ),

    taskpolygonsnoindex AS (
        SELECT (st_dump(st_polygonize(s.geom))).geom AS geom
        FROM simplifiedlines AS s
    )

    SELECT
        tpni.*,
        row_number() OVER () AS taskid
    FROM taskpolygonsnoindex AS tpni
);
ALTER TABLE taskpolygons ADD PRIMARY KEY (taskid);
SELECT populate_geometry_columns('public.taskpolygons'::regclass);
CREATE INDEX taskpolygons_idx
ON taskpolygons
USING gist (geom);

--VACUUM ANALYZE taskpolygons;

-- Clean results (nuke or merge polygons without features in them)
