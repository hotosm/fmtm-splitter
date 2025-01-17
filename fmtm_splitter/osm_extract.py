#!/bin/python3

# Copyright (c) 2022 Humanitarian OpenStreetMap Team
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     FMTM-Splitter is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with FMTM-Splitter.  If not, see <https:#www.gnu.org/licenses/>.
#
"""Class and helper methods for task splitting."""

import logging
from io import BytesIO

from geojson import FeatureCollection
from osm_rawdata.postgres import PostgresClient

# Instantiate logger
log = logging.getLogger(__name__)


def generate_osm_extract(
    aoi_featcol: FeatureCollection, extract_type: str
) -> FeatureCollection:
    """Generate OSM extract based on the specified type from AOI FeatureCollection."""
    try:
        config_data_map = {
            "extracts": """
            select:
            from:
                - nodes
                - ways_poly
                - ways_line
            where:
                tags:
                - building: not null
                - highway: not null
                - waterway: not null
                - railway: not null
                - aeroway: not null
            """,
            "lines": """
            select:
            from:
                - nodes
                - ways_line
            where:
                tags:
                - highway: not null
                - waterway: not null
                - railway: not null
                - aeroway: not null
            """,
        }
        config_data = config_data_map.get(extract_type)
        if not config_data:
            raise ValueError(f"Invalid extract type: {extract_type}")

        config_bytes = BytesIO(config_data.encode())
        pg = PostgresClient("underpass", config_bytes)
        return pg.execQuery(
            aoi_featcol,
            extra_params={"fileName": "fmtm_splitter", "useStWithin": False},
        )
    except Exception as e:
        log.error(f"Error during OSM extract generation: {e}")
        raise RuntimeError(f"Failed to generate OSM extract: {e}") from e
