/*
Licence: GPLv3 <https://www.gnu.org/licenses/gpl-3.0.html>
Part of the HOT Field Mapping Tasking Manager (FMTM)

This script splits an Area of Interest into task polygons based on OpenStreetMap lines (roads, waterways, and railways) and buildings. More information in the adjacent file task_splitting_readme.md.
*/

--*************************Split by OSM lines***********************
-- Nuke whatever was there before
DROP TABLE IF EXISTS polygonsnocount;
-- Create a new polygon layer of splits by lines
CREATE TABLE polygonsnocount AS (
    -- The Area of Interest provided by the person creating the project
    WITH aoi AS (
        SELECT * FROM "project_aoi"
    ),

    -- Extract all lines to be used as splitlines from a table of lines
    -- with the schema from Underpass (all tags as jsonb column called 'tags')
    -- TODO: add polygons (closed ways in OSM) with a 'highway' tag;
    -- some features such as roundabouts appear as polygons.
    -- TODO: add waterway polygons; now a beach doesn't show up as a splitline.
    -- TODO: these tags should come from another table rather than hardcoded
    -- so that they're easily configured during project creation.
    splitlines AS (
        SELECT ST_INTERSECTION(a.geom, l.geom) AS geom
        FROM aoi AS a, "ways_line" AS l
        WHERE ST_INTERSECTS(a.geom, l.geom)
        -- TODO: these tags should come from a config table
        -- All highways, waterways, and railways
        AND (
            tags ->> 'highway' IS NOT NULL
            OR tags ->> 'waterway' IS NOT NULL
            OR tags ->> 'railway' IS NOT NULL
        )
    ),

    -- Merge all lines, necessary so that the polygonize function works later
    merged AS (
        SELECT ST_LINEMERGE(ST_UNION(splitlines.geom)) AS geom
        FROM splitlines
    ),

    -- Combine the boundary of the AOI with the splitlines
    -- First extract the Area of Interest boundary as a line
    boundary AS (
        SELECT ST_BOUNDARY(geom) AS geom
        FROM aoi
    ),

    -- Then combine it with the splitlines
    comb AS (
        SELECT ST_UNION(boundary.geom, merged.geom) AS geom
        FROM boundary, merged
    ),

    -- TODO add closed ways from OSM to lines (roundabouts etc)
    -- Create a polygon for each area enclosed by the splitlines
    splitpolysnoindex AS (
        SELECT (ST_DUMP(ST_POLYGONIZE(comb.geom))).geom AS geom
        FROM comb
    ),

    -- Add an index column to the split polygons
    splitpolygons AS (
        SELECT
            spni.*,
            ST_TRANSFORM(spni.geom, 4326)::geography AS geog,
            ROW_NUMBER() OVER () AS polyid
        FROM splitpolysnoindex AS spni
    )

    SELECT * FROM splitpolygons
);
-- Make that index column a primary key
ALTER TABLE polygonsnocount ADD PRIMARY KEY (polyid);
-- Properly register geometry column (makes QGIS happy)
SELECT POPULATE_GEOMETRY_COLUMNS('public.polygonsnocount'::regclass);
-- Add a spatial index (vastly improves performance for a lot of operations)
CREATE INDEX polygonsnocount_idx
ON polygonsnocount
USING gist (geom);
-- Clean up the table which may have gaps and stuff from spatial indexing
VACUUM ANALYZE polygonsnocount;

-- ************************Grab the buildings**************************
-- While we're at it, grab the ID of the polygon the buildings fall within.
-- TODO add outer rings of buildings from relations table of OSM export
DROP TABLE IF EXISTS buildings;
CREATE TABLE buildings AS (
    SELECT
        b.*,
        polys.polyid
    FROM "ways_poly" AS b, polygonsnocount AS polys
    WHERE
        ST_INTERSECTS(polys.geom, ST_CENTROID(b.geom))
        AND b.tags ->> 'building' IS NOT NULL
);
ALTER TABLE buildings ADD PRIMARY KEY (osm_id);
-- Properly register geometry column (makes QGIS happy)
SELECT POPULATE_GEOMETRY_COLUMNS('public.buildings'::regclass);
-- Add a spatial index (vastly improves performance for a lot of operations)
CREATE INDEX buildings_idx
ON buildings
USING gist (geom);
-- Clean up the table which may have gaps and stuff from spatial indexing
VACUUM ANALYZE buildings;

--**************************Count features in polygons*****************
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
        LEFT JOIN "buildings" AS b
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
VACUUM ANALYZE splitpolygons;

DROP TABLE polygonsnocount;

DROP TABLE IF EXISTS lowfeaturecountpolygons;
CREATE TABLE lowfeaturecountpolygons AS (
    -- Grab the polygons with fewer than the requisite number of features
    WITH lowfeaturecountpolys AS (
        SELECT *
        FROM splitpolygons AS p
        -- TODO: feature count should not be hard-coded
        WHERE p.numfeatures < 5
    ),

    -- Find the neighbors of the low-feature-count polygons
    -- Store their ids as n_polyid, numfeatures as n_numfeatures, etc
    allneighborlist AS (
        SELECT
            p.*,
            pf.polyid AS n_polyid,
            pf.area AS n_area,
            p.numfeatures AS n_numfeatures,
            -- length of shared boundary to make nice merge decisions 
            ST_LENGTH2D(ST_INTERSECTION(p.geom, pf.geom)) AS sharedbound
        FROM lowfeaturecountpolys AS p
        INNER JOIN splitpolygons AS pf
            -- Anything that touches
            ON ST_TOUCHES(p.geom, pf.geom)
            -- But eliminate those whose intersection is a point, because
            -- polygons that only touch at a corner shouldn't be merged
            AND ST_GEOMETRYTYPE(ST_INTERSECTION(p.geom, pf.geom)) != 'ST_Point'
        -- Sort first by polyid of the low-feature-count polygons
        -- Then by descending featurecount and area of the 
        -- high-feature-count neighbors (area is in case of equal 
        -- featurecounts, we'll just pick the biggest to add to)
        ORDER BY p.polyid ASC, p.numfeatures DESC, pf.area DESC
    -- OR, maybe for more aesthetic merges:
    -- order by p.polyid, sharedbound desc
    )

    SELECT DISTINCT ON (a.polyid) * FROM allneighborlist AS a
);
ALTER TABLE lowfeaturecountpolygons ADD PRIMARY KEY (polyid);
SELECT POPULATE_GEOMETRY_COLUMNS('public.lowfeaturecountpolygons'::regclass);
CREATE INDEX lowfeaturecountpolygons_idx
ON lowfeaturecountpolygons
USING gist (geom);
VACUUM ANALYZE lowfeaturecountpolygons;

--****************Merge low feature count polygons with neighbors*******



--****************Cluster buildings*************************************
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

    -- Cluster the buildings within each splitpolygon. The second term in the
    -- call to the ST_ClusterKMeans function is the number of clusters to create,
    -- so we're dividing the number of features by a constant (10 in this case)
    -- to get the number of clusters required to get close to the right number
    -- of features per cluster.
    -- TODO: This should certainly not be a hardcoded, the number of features
    --       per cluster should come from a project configuration table
    buildingstocluster AS (
        SELECT * FROM buildingswithcount AS bc
        WHERE bc.numfeatures > 0
    ),

    clusteredbuildingsnocombineduid AS (
        SELECT
            *,
            ST_CLUSTERKMEANS(geom, ((b.numfeatures / 5) + 1)::integer)
                OVER (PARTITION BY polyid)
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
ALTER TABLE clusteredbuildings ADD PRIMARY KEY (osm_id);
SELECT POPULATE_GEOMETRY_COLUMNS('public.clusteredbuildings'::regclass);
CREATE INDEX clusteredbuildings_idx
ON clusteredbuildings
USING gist (geom);
VACUUM ANALYZE clusteredbuildings;

--*****************Densify dumped building nodes******************
DROP TABLE IF EXISTS dumpedpoints;
CREATE TABLE dumpedpoints AS (
    SELECT
        cb.osm_id,
        cb.polyid,
        cb.cid,
        cb.clusteruid,
        -- POSSIBLE BUG: PostGIS' Voronoi implementation seems to panic
        -- with segments less than 0.00004 degrees.
        -- Should probably use geography instead of geometry
        (ST_DUMPPOINTS(ST_SEGMENTIZE(cb.geom, 0.00001))).geom
    FROM clusteredbuildings AS cb
);
SELECT POPULATE_GEOMETRY_COLUMNS('public.dumpedpoints'::regclass);
CREATE INDEX dumpedpoints_idx
ON dumpedpoints
USING gist (geom);
VACUUM ANALYZE dumpedpoints;

--*******************voronoia****************************************
DROP TABLE IF EXISTS voronoids;
CREATE TABLE voronoids AS (
    SELECT
        ST_INTERSECTION((ST_DUMP(ST_VORONOIPOLYGONS(
            ST_COLLECT(points.geom)
        ))).geom,
        sp.geom) AS geom
    FROM dumpedpoints AS points,
        splitpolygons AS sp
    WHERE ST_CONTAINS(sp.geom, points.geom)
    GROUP BY sp.geom
);
CREATE INDEX voronoids_idx
ON voronoids
USING gist (geom);
VACUUM ANALYZE voronoids;

DROP TABLE IF EXISTS voronois;
CREATE TABLE voronois AS (
    SELECT
        p.clusteruid,
        v.geom
    FROM voronoids AS v, dumpedpoints AS p
    WHERE ST_WITHIN(p.geom, v.geom)
);
CREATE INDEX voronois_idx
ON voronois
USING gist (geom);
VACUUM ANALYZE voronois;
DROP TABLE voronoids;

DROP TABLE IF EXISTS taskpolygons;
CREATE TABLE taskpolygons AS (
    SELECT
        clusteruid,
        ST_UNION(geom) AS geom
    FROM voronois
    GROUP BY clusteruid
);
CREATE INDEX taskpolygons_idx
ON taskpolygons
USING gist (geom);
VACUUM ANALYZE taskpolygons;

--*****************************Simplify*******************************
-- Extract unique line segments
DROP TABLE IF EXISTS simplifiedpolygons;
CREATE TABLE simplifiedpolygons AS (
    --Convert task polygon boundaries to linestrings
    WITH rawlines AS (
        SELECT
            tp.clusteruid,
            ST_BOUNDARY(tp.geom) AS geom
        FROM taskpolygons AS tp
    ),

    -- Union, which eliminates duplicates from adjacent polygon boundaries
    unionlines AS (
        SELECT ST_UNION(l.geom) AS geom FROM rawlines AS l
    ),

    -- Dump, which gives unique segments.
    segments AS (
        SELECT (ST_DUMP(l.geom)).geom AS geom
        FROM unionlines AS l
    ),

    agglomerated AS (
        SELECT ST_LINEMERGE(ST_UNARYUNION(ST_COLLECT(s.geom))) AS geom
        FROM segments AS s
    ),

    simplifiedlines AS (
        SELECT ST_SIMPLIFY(a.geom, 0.000075) AS geom
        FROM agglomerated AS a
    )

    SELECT (ST_DUMP(ST_POLYGONIZE(s.geom))).geom AS geom
    FROM simplifiedlines AS s
);
CREATE INDEX simplifiedpolygons_idx
ON simplifiedpolygons
USING gist (geom);
VACUUM ANALYZE simplifiedpolygons;

-- Clean results (nuke or merge polygons without features in them)
