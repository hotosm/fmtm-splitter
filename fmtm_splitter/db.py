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
from typing import Any, Dict, List, Union

import psycopg2
from psycopg2.extensions import register_adapter
from psycopg2.extras import Json, register_uuid
from shapely.geometry import Polygon

log = logging.getLogger(__name__)


def create_connection(
    db: Union[str, psycopg2.extensions.connection],
) -> psycopg2.extensions.connection:
    """Get db connection from existing psycopg2 connection, or URL string.

    Args:
        db (str, psycopg2.extensions.connection):
            string or existing db connection.
            If `db` is a string, a new connection is generated.
            If `db` is a psycopg2 connection, the connection is re-used.

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
    else:
        msg = "The `db` variable is not a valid string or psycopg2 connection."
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
            geom GEOMETRY(GEOMETRY, 4326)
        );

        CREATE TABLE ways_poly (
            id SERIAL PRIMARY KEY,
            osm_id VARCHAR NULL,
            geom GEOMETRY(GEOMETRY, 4326) NOT NULL,
            tags JSONB NULL
        );

        CREATE TABLE ways_line (
            id SERIAL PRIMARY KEY,
            osm_id VARCHAR NULL,
            geom GEOMETRY(GEOMETRY, 4326) NOT NULL,
            tags JSONB NULL
        );
    """
    log.debug(
        "Running tables create command for 'project_aoi', 'ways_poly', 'ways_line'"
    )
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
        "DROP TABLE IF EXISTS unsimplifiedtaskpolygons CASCADE; "
        "DROP TABLE IF EXISTS splitpolygons CASCADE; "
        "DROP TABLE IF EXISTS project_aoi CASCADE; "
        "DROP TABLE IF EXISTS ways_poly CASCADE; "
        "DROP TABLE IF EXISTS ways_line CASCADE;"
    )
    log.debug(f"Running tables drop command: {drop_cmd}")
    cur = conn.cursor()
    cur.execute(drop_cmd)


def aoi_to_postgis(conn: psycopg2.extensions.connection, geom: Polygon) -> None:
    """Export a GeoDataFrame to the project_aoi table in PostGIS.

    Uses a new cursor on existing connection, but not committed directly.

    Args:
        geom (Polygon): The shapely geom to insert.
        conn (psycopg2.extensions.connection): The PostgreSQL connection.

    Returns:
        None
    """
    log.debug("Adding AOI to project_aoi table")

    sql_insert = """
        INSERT INTO project_aoi (geom)
        VALUES (ST_SetSRID(CAST(%s AS GEOMETRY), 4326))
        RETURNING id, geom;
    """

    try:
        with conn.cursor() as cur:
            cur.execute(sql_insert, (geom.wkb_hex,))
        cur.close()

    except Exception as e:
        log.error(f"Error during database operations: {e}")
        conn.rollback()  # Rollback in case of error


def insert_geom(
    conn: psycopg2.extensions.connection, table_name: str, data: List[Dict[str, Any]]
) -> None:
    """Insert geometries into the database.

    Such as:
    - LineStrings
    - Polygons

    Handles both cases: with or without tags and osm_id.

    Args:
        conn (psycopg2.extensions.connection): The PostgreSQL connection.
        table_name (str): The name of the table to insert data into.
        data(List[dict]): Values of features to be inserted; geom, tags.

    Returns:
        None
    """
    placeholders = ", ".join(data[0].keys())
    values = [tuple(record.values()) for record in data]

    sql_query = f"""
    INSERT INTO {table_name} ({placeholders})
    VALUES ({", ".join(["%s"] * len(data[0]))})
    """
    try:
        with conn.cursor() as cursor:
            cursor.executemany(sql_query, values)
            conn.commit()
    except Exception as e:
        log.error(f"Error executing query: {e}")
        conn.rollback()  # Rollback transaction on error
