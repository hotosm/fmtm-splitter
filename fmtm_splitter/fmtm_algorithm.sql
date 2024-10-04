DROP TABLE IF EXISTS polygonsnocount;
-- Create a new polygon layer of splits by lines

DO $$
    DECLARE 
    lines_count INTEGER;
    num_buildings INTEGER;
BEGIN
    -- Check if ways_line has any data
    SELECT COUNT(*) INTO lines_count
    FROM "ways_line" l
    WHERE (
        (l.tags->>'highway' IS NOT NULL AND 
        l.tags->>'highway' NOT IN ('unclassified', 'residential', 'service', 'pedestrian', 'track', 'bus_guideway'))
        OR l.tags->>'waterway' IS NOT NULL
        OR l.tags->>'railway' IS NOT NULL
    );
    IF lines_count > 0 THEN
    CREATE TABLE polygonsnocount AS (
        -- The Area of Interest provided by the person creating the project
        WITH aoi AS (
            SELECT * FROM "project_aoi"
        )
        -- Extract all lines to be used as splitlines from a table of lines
        -- with the schema from Underpass (all tags as jsonb column called 'tags')
        -- TODO: add polygons (closed ways in OSM) with a 'highway' tag;
        -- some features such as roundabouts appear as polygons.
        -- TODO: add waterway polygons; now a beach doesn't show up as a splitline.
        -- TODO: these tags should come from another table rather than hardcoded
        -- so that they're easily configured during project creation.
        , splitlines AS (
            SELECT ST_Intersection(a.geom, l.geom) AS geom
            FROM aoi a
            JOIN "ways_line" l ON ST_Intersects(a.geom, l.geom)
            WHERE (
                (l.tags->>'highway' IS NOT NULL AND 
                l.tags->>'highway' NOT IN ('unclassified', 'residential', 'service', 'pedestrian', 'track', 'bus_guideway')) -- TODO: update(add/remove) this based on the requirements later
                OR l.tags->>'waterway' IS NOT NULL
                OR l.tags->>'railway' IS NOT NULL
            )
        )
            
        --     SELECT * from lines_view l
        --    WHERE (
        --         (l.tags->>'highway' IS NOT NULL AND 
        --         l.tags->>'highway' NOT IN ('unclassified', 'residential', 'service', 'pedestrian', 'track', 'bus_guideway'))
        --         OR l.tags->>'waterway' IS NOT NULL
        --         OR l.tags->>'railway' IS NOT NULL
        --     )
        -- )
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

DROP TABLE polygonsnocount;


DROP TABLE IF EXISTS lowfeaturecountpolygons;
CREATE TABLE lowfeaturecountpolygons AS (
-- Grab the polygons with fewer than the requisite number of features
    WITH lowfeaturecountpolys AS (
        SELECT *
        FROM splitpolygons AS p
        -- TODO: feature count should not be hard-coded
        WHERE p.numfeatures < %(num_buildings)s
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
-- VACUUM ANALYZE lowfeaturecountpolygons;


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
    -- call to the ST_ClusterKMeans function is the number of clusters to 
    -- create, so we're dividing the number of features by a constant 
    -- (10 in this case) to get the number of clusters required to get close
    -- to the right number of features per cluster.
    -- TODO: This should certainly not be a hardcoded, the number of features
    --       per cluster should come from a project configuration table
    buildingstocluster AS (
        SELECT * FROM buildingswithcount AS bc
        WHERE bc.numfeatures > 0
    ),

    clusteredbuildingsnocombineduid AS (
        SELECT
            *,
            ST_CLUSTERKMEANS(
                b.geom,
                CAST((b.numfeatures / %(num_buildings)s) + 1 AS integer)
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
-- VACUUM ANALYZE clusteredbuildings;


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
        (ST_DUMPPOINTS(ST_SEGMENTIZE(cb.geom, 0.00004))).geom
    FROM clusteredbuildings AS cb
);
SELECT POPULATE_GEOMETRY_COLUMNS('public.dumpedpoints'::regclass);
CREATE INDEX dumpedpoints_idx
ON dumpedpoints
USING gist (geom);
-- VACUUM ANALYZE dumpedpoints;

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
-- VACUUM ANALYZE voronoids;

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
-- VACUUM ANALYZE voronois;
DROP TABLE voronoids;

DROP TABLE IF EXISTS unsimplifiedtaskpolygons;
CREATE TABLE unsimplifiedtaskpolygons AS (
    SELECT
        clusteruid,
        ST_UNION(geom) AS geom
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
            ST_BOUNDARY(utp.geom) AS geom
        FROM unsimplifiedtaskpolygons AS utp
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
    ),

    taskpolygonsnoindex AS (
        SELECT (ST_DUMP(ST_POLYGONIZE(s.geom))).geom AS geom
        FROM simplifiedlines AS s
    )

    SELECT
        tpni.*,
        ROW_NUMBER() OVER () AS taskid
    FROM taskpolygonsnoindex AS tpni
);

-- ALTER TABLE taskpolygons ADD PRIMARY KEY(taskid);

-- Step 1: Identify polygons without any buildings
DROP TABLE IF EXISTS no_building_polygons;
CREATE TABLE no_building_polygons AS (
    SELECT
        tp.*,
        tp.geom AS no_building_geom
    FROM taskpolygons AS tp
    LEFT JOIN buildings AS b ON ST_INTERSECTS(tp.geom, b.geom)
    WHERE b.geom IS NULL
);

-- Step 2: Identify neighboring polygons
DROP TABLE IF EXISTS neighboring_polygons;
CREATE TABLE neighboring_polygons AS (
    SELECT
        nb.*,
        nb.geom AS neighbor_geom,
        nb_building_count,
        nbp.no_building_geom
    FROM taskpolygons AS nb
    INNER JOIN no_building_polygons AS nbp
        -- Finds polygons that touch each other
        ON ST_TOUCHES(nbp.no_building_geom, nb.geom)
    LEFT JOIN (
        -- Step 3: Count buildings in the neighboring polygons
        SELECT
            nb.geom,
            COUNT(b.geom) AS nb_building_count
        FROM taskpolygons AS nb
        LEFT JOIN buildings AS b ON ST_INTERSECTS(nb.geom, b.geom)
        GROUP BY nb.geom
    ) AS building_counts
        ON nb.geom = building_counts.geom
);

-- Step 4: Find the optimal neighboring polygon to avoid,
-- same polygons with the smallest number of buildings merging into
-- multiple neighboring polygons
DROP TABLE IF EXISTS optimal_neighbors;
CREATE TABLE optimal_neighbors AS (
    SELECT
        nbp.no_building_geom,
        nbp.neighbor_geom
    FROM neighboring_polygons AS nbp
    WHERE nbp.nb_building_count = (
        SELECT MIN(nb_building_count)
        FROM neighboring_polygons AS np
        WHERE np.no_building_geom = nbp.no_building_geom
    )
);

-- Step 5: Merge the small polygons with their optimal neighboring polygons
UPDATE taskpolygons tp
SET geom = ST_UNION(tp.geom, nbp.no_building_geom)
FROM optimal_neighbors AS nbp
WHERE tp.geom = nbp.neighbor_geom;
DELETE FROM taskpolygons
WHERE geom IN (
    SELECT no_building_geom
    FROM no_building_polygons
);


DROP TABLE IF EXISTS no_building_polygons;
DROP TABLE IF EXISTS neighboring_polygons;

SELECT POPULATE_GEOMETRY_COLUMNS('public.taskpolygons'::regclass);
CREATE INDEX taskpolygons_idx
ON taskpolygons
USING gist (geom);
-- VACUUM ANALYZE taskpolygons;

-- Generate GeoJSON output
SELECT
    JSONB_BUILD_OBJECT(
        'type', 'FeatureCollection',
        'features', JSONB_AGG(feature)
    )
FROM (
    SELECT
        JSONB_BUILD_OBJECT(
            'type', 'Feature',
            'geometry', ST_ASGEOJSON(geom)::jsonb,
            'properties', JSONB_BUILD_OBJECT()
        ) AS feature
    FROM taskpolygons
) AS features;
