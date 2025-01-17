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
"""helper functions to parse data for task splitting."""

import json
import logging
import math
from pathlib import Path
from typing import Optional, Tuple, Union

# Instantiate logger
log = logging.getLogger(__name__)


def prepare_sql_query(sql_file: Optional[Union[str, Path]], default_path: Path) -> str:
    """Load SQL query from a file or fallback to default."""
    if not sql_file:
        sql_file = default_path
    with open(sql_file, "r") as sql:
        return sql.read()


def json_str_to_dict(json_item: Union[str, dict]) -> dict:
    """Convert a JSON string to dict."""
    if isinstance(json_item, dict):
        return json_item
    if isinstance(json_item, str):
        try:
            return json.loads(json_item)
        except json.JSONDecodeError:
            msg = f"Error decoding key in GeoJSON: {json_item}"
            log.error(msg)
            # Set tags to empty, skip feature
            return {}


def meters_to_degrees(meters: float, reference_lat: float) -> Tuple[float, float]:
    """Converts meters to degrees at a given latitude.

    Using WGS84 ellipsoidal calculations.

    Args:
        meters (float): The distance in meters to convert.
        reference_lat (float): The latitude at which to ,
        perform the conversion (in degrees).

    Returns:
        Tuple[float, float]: Degree values for latitude and longitude.
    """
    # INFO:
    # The geodesic distance is the shortest distance on the surface
    # of an ellipsoidal model of the earth

    lat_rad = math.radians(reference_lat)

    # Using WGS84 parameters
    a = 6378137.0  # Semi-major axis in meters
    f = 1 / 298.257223563  # Flattening factor

    # Applying formula
    e2 = (2 * f) - (f**2)  # Eccentricity squared
    n = a / math.sqrt(
        1 - e2 * math.sin(lat_rad) ** 2
    )  # Radius of curvature in the prime vertical
    m = (
        a * (1 - e2) / (1 - e2 * math.sin(lat_rad) ** 2) ** (3 / 2)
    )  # Radius of curvature in the meridian

    lat_deg_change = meters / m  # Latitude change in degrees
    lon_deg_change = meters / (n * math.cos(lat_rad))  # Longitude change in degrees

    # Convert changes to degrees by dividing by radians to degrees
    lat_deg_change = math.degrees(lat_deg_change)
    lon_deg_change = math.degrees(lon_deg_change)

    return lat_deg_change, lon_deg_change
