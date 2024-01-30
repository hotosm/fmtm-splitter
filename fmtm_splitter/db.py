# Copyright (c) 2022, 2023 Humanitarian OpenStreetMap Team
# This file is part of fmtm-splitter.
#
#     fmtm-splitter is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     fmtm-splitter is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with fmtm-splitter.  If not, see <https:#www.gnu.org/licenses/>.
#
"""DB models for temporary tables in splitBySQL."""
import logging
import warnings
from typing import Union

import geopandas as gpd
import psycopg2
from psycopg2.extensions import register_adapter
from psycopg2.extras import Json, execute_values, register_uuid

try:
    import sqlalchemy

    _sqlalchemy_import = True
except ImportError:
    _sqlalchemy_import = False

log = logging.getLogger(__name__)


def create_connection(db: Union[str, psycopg2.extensions.connection]) -> psycopg2.extensions.connection:
    """Get db connection from existing psycopg2 connection, or URL string.

    Args:
        db (str, psycopg2.extensions.connection, sqlalchemy.orm.session.Session):
            string or existing db connection.
            If `db` is a string, a new connection is generated.
            If `db` is a psycopg connection, the connection is re-used.
            If `db` is a sqlalchemy.orm.session.Session object, the connection
                is also reused.

    Returns:
        conn: DBAPI connection object to generate cursors from.
    """
    # Makes Postgres UUID, JSONB usable, else error
    register_uuid()
    register_adapter(dict, Json)

    if isinstance(db, psycopg2.extensions.connection):
        conn = db
    elif isinstance(db, str):
        conn = psycopg2.connect(db)
    elif _sqlalchemy_import and isinstance(db, sqlalchemy.orm.session.Session):
        conn = db.connection().connection
    else:
        msg = "The `db` variable is not a valid string, psycopg connection, " "or SQLAlchemy Session."
        log.error(msg)
        raise ValueError(msg)

    return conn


def close_connection(conn: psycopg2.extensions.connection):
    """Close the db connection."""
    # Execute all commands in a transaction before closing
    try:
        conn.commit()
    except Exception as e:
        log.error(e)
        log.error("Error committing psycopg2 transaction to db")
    finally:
        conn.close()


def create_tables(conn: psycopg2.extensions.connection):
    """Create tables required for splitting.

    Uses a new cursor on existing connection, but not committed directly.
    """
    # First drop tables if they exist
    drop_tables(conn)

    create_cmd = """
        CREATE TABLE project_aoi (
            id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
            geom GEOMETRY(GEOMETRY, 4326),
            tags JSONB
        );

        CREATE TABLE ways_poly (
            id SERIAL PRIMARY KEY,
            project_id VARCHAR,
            osm_id VARCHAR,
            geom GEOMETRY(GEOMETRY, 4326),
            tags JSONB
        );

        CREATE TABLE ways_line (
            id SERIAL PRIMARY KEY,
            project_id VARCHAR,
            osm_id VARCHAR,
            geom GEOMETRY(GEOMETRY, 4326),
            tags JSONB
        );
    """
    log.debug("Running tables create command for 'project_aoi', 'ways_poly', 'ways_line'")
    cur = conn.cursor()
    cur.execute(create_cmd)


def drop_tables(conn: psycopg2.extensions.connection):
    """Drop all tables used for splitting.

    Uses a new cursor on existing connection, but not committed directly.
    """
    drop_cmd = (
        "DROP VIEW IF EXISTS lines_view;"
        "DROP TABLE IF EXISTS buildings CASCADE; "
        "DROP TABLE IF EXISTS clusteredbuildings CASCADE; "
        "DROP TABLE IF EXISTS dumpedpoints CASCADE; "
        "DROP TABLE IF EXISTS lowfeaturecountpolygons CASCADE; "
        "DROP TABLE IF EXISTS voronois CASCADE; "
        "DROP TABLE IF EXISTS taskpolygons CASCADE; "
        "DROP TABLE IF EXISTS splitpolygons CASCADE;"
        "DROP TABLE IF EXISTS project_aoi CASCADE; "
        "DROP TABLE IF EXISTS ways_poly CASCADE; "
        "DROP TABLE IF EXISTS ways_line CASCADE;"
    )
    log.debug(f"Running tables drop command: {drop_cmd}")
    cur = conn.cursor()
    cur.execute(drop_cmd)


def gdf_to_postgis(gdf: gpd.GeoDataFrame, conn: psycopg2.extensions.connection, table_name: str, geom_name: str = "geom") -> None:
    """Export a GeoDataFrame to the project_aoi table in PostGIS.

    Built-in geopandas to_wkb uses shapely underneath.

    Uses a new cursor on existing connection, but not committed directly.

    Args:
        gdf (gpd.GeoDataFrame): The GeoDataFrame to export.
        conn (psycopg2.extensions.connection): The PostgreSQL connection.
        table_name (str): The name of the table to insert data into.
        geom_name (str, optional): The name of the geometry column. Defaults to "geom".

    Returns:
        None
    """
    # Only use dataframe copy, else the geom is transformed to WKBElement
    gdf = gdf.copy()

    # Rename existing geometry column if it doesn't match
    if geom_name not in gdf.columns:
        gdf = gdf.rename(columns={gdf.geometry.name: geom_name}).set_geometry(geom_name, crs=gdf.crs)

    log.debug("Converting geodataframe geom to wkb hex string")
    # Ignore warning 'Geometry column does not contain geometry'
    warnings.filterwarnings("ignore", category=UserWarning, module="fmtm_splitter.db")
    gdf[geom_name] = gdf[geom_name].to_wkb(hex=True, include_srid=True)
    warnings.filterwarnings("default", category=UserWarning, module="fmtm_splitter.db")

    # Build numpy array for db insert
    tuples = [tuple(x) for x in gdf.to_numpy()]
    cols = ",".join(list(gdf.columns))
    query = "INSERT INTO %s(%s) VALUES %%s" % (table_name, cols)

    cur = conn.cursor()
    execute_values(cur, query, tuples)


def insert_geom(cur: psycopg2.extensions.cursor, table_name: str, **kwargs) -> None:
    """Insert an OSM geometry into the database.

    Does not commit the values automatically.

    Args:
        cur (psycopg2.extensions.cursor): The PostgreSQL cursor.
        table_name (str): The name of the table to insert data into.
        **kwargs: Keyword arguments representing the values to be inserted.

    Returns:
        None
    """
    query = f"INSERT INTO {table_name}(project_id,geom,osm_id,tags) " "VALUES (%(project_id)s,%(geom)s,%(osm_id)s,%(tags)s)"
    cur.execute(query, kwargs)
