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
"""The main LiteStar app."""

from logging import getLogger

from geojson_pydantic import FeatureCollection
from litestar import Litestar, post
from litestar.config.compression import CompressionConfig
from litestar.logging import LoggingConfig
from litestar.openapi.config import OpenAPIConfig
from litestar.openapi.plugins import ScalarRenderPlugin

from api.schemas import SplitByAverageBuilding, SplitBySquare
from api.settings import Settings
from fmtm_splitter.splitter import split_by_sql, split_by_square

settings = Settings()
log = getLogger(__name__)


@post("/average-building/")
async def aoi_split_by_average_building(
    data: SplitByAverageBuilding,
) -> FeatureCollection:
    """Split an AOI by average number of building per task."""
    try:
        features = split_by_sql(
            data.aoi.model_dump(),
            settings.DB_URL,
            num_buildings=data.num_buildings,
            osm_extract=data.osm_extract.model_dump() if data.osm_extract else None,
        )
        return features
    except Exception as exc:
        raise ValueError(f"Failed to split AOI: {str(exc)}") from exc


@post("/squares/")
async def aoi_split_by_square(data: SplitBySquare) -> FeatureCollection:
    """Split an AOI into squares."""
    try:
        features = split_by_square(
            data.aoi.model_dump(),
            settings.DB_URL,
            meters=data.dimension,
            osm_extract=data.osm_extract.model_dump() if data.osm_extract else None,
        )
        return features
    except Exception as exc:
        raise ValueError(f"Failed to split AOI: {str(exc)}") from exc


app = Litestar(
    debug=settings.DEBUG,
    route_handlers=[aoi_split_by_average_building, aoi_split_by_square],
    # As a microservice, it's likely this is behind a path prefix,
    # but it this could also be set to None if on a subdomain instead
    path="/fmtm-splitter",
    on_startup=[lambda: print("Starting server.")],
    on_shutdown=[lambda: print("Stopping server.")],
    logging_config=LoggingConfig(
        root={
            "level": "DEBUG" if settings.DEBUG else "INFO",
            "handlers": ["queue_listener"],
        },
        formatters={
            "standard": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            }
        },
    ),
    compression_config=CompressionConfig(backend="brotli"),
    openapi_config=OpenAPIConfig(
        title="FMTM Splitter",
        description="A small microservice wrapping the functionality of fmtm-splitter.",
        version="0.1.0",
        render_plugins=[ScalarRenderPlugin()],
        path="/docs/",
    ),
)
