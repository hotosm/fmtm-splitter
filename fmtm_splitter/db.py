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
from typing import Union
from uuid import uuid4

from geoalchemy2 import Geometry
from sqlalchemy import (
    Column,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

log = logging.getLogger(__name__)


def get_engine(db: Union[str, Session]):
    """Get engine from existing Session, or connection string.

    If `db` is a connection string, a new engine is generated.
    """
    if isinstance(db, Session):
        return db.get_bind()
    elif isinstance(db, str):
        return create_engine(db)
    else:
        msg = "The `db` variable is not a valid string or Session"
        log.error(msg)
        raise ValueError(msg)


def new_session(engine: Engine):
    """Get session using engine.

    Be sure to use in a with statement.
    with new_session(conn) as session:
        session.add(xxx)
        session.commit()
    """
    return sessionmaker(engine)


class Base(DeclarativeBase):
    """Wrapper for DeclarativeBase creating all tables."""

    pass


class DbProjectAOI(Base):
    """The AOI geometry for a project."""

    __tablename__ = "project_aoi"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    geom = Column(Geometry(geometry_type="GEOMETRY", srid=4326))
    tags = Column(JSONB)


class DbBuildings(Base):
    """Associated OSM buildings for a project."""

    __tablename__ = "ways_poly"

    id = Column(Integer, primary_key=True)
    project_id = Column(String)
    osm_id = Column(String)
    geom = Column(Geometry(geometry_type="GEOMETRY", srid=4326))
    tags = Column(JSONB)


class DbOsmLines(Base):
    """Associated OSM ways for a project."""

    __tablename__ = "ways_line"

    id = Column(Integer, primary_key=True)
    project_id = Column(String)
    osm_id = Column(String)
    geom = Column(Geometry(geometry_type="GEOMETRY", srid=4326))
    tags = Column(JSONB)
