# Copyright (c) Humanitarian OpenStreetMap Team
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
"""Schemas / dataclasses for input output."""

from dataclasses import dataclass, field
from typing import Annotated, Optional

from geojson_pydantic import FeatureCollection, Polygon
from litestar.params import Body

from api.settings import Settings

settings = Settings()


def example_aoi_input() -> FeatureCollection | None:
    """Provide example AOI input for debugging."""
    if settings.DEBUG:
        return {
            "type": "Polygon",
            "coordinates": [
                [
                    [85.29998911024427, 27.714008043780694],
                    [85.29998911024427, 27.710892349952076],
                    [85.30478315714117, 27.710892349952076],
                    [85.30478315714117, 27.714008043780694],
                    [85.29998911024427, 27.714008043780694],
                ]
            ],
        }
    return None


@dataclass
class AoiInput:
    """Input AOI Polygon GeoJSON."""

    aoi: Annotated[
        Polygon, Body(title="Upload AOI", description="Upload a GeoJSON Polygon.")
    ] = field(default_factory=example_aoi_input)


@dataclass
class DataExtract:
    """Optional data extract FeatureCollection."""

    osm_extract: Annotated[
        Optional[FeatureCollection],
        Body(
            title="Upload Linear Features",
            description="We can split by roads, rivers, railways, etc.",
        ),
    ] = None


@dataclass
class SplitByAverageBuilding(AoiInput, DataExtract):
    """Specify average number of buildings per task."""

    num_buildings: Annotated[
        int,
        Body(
            title="Average Number of Buildings", description="For the task area split."
        ),
    ] = 5


@dataclass
class SplitBySquare(AoiInput, DataExtract):
    """Specify dimension of squares to split into."""

    dimension: Annotated[
        int,
        Body(title="Size of the squares", description="Length of a side in meters."),
    ] = 100
