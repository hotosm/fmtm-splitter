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
ARG PYTHON_IMG_TAG=3.12
ARG UV_IMG_TAG=0.5.2
FROM ghcr.io/astral-sh/uv:${UV_IMG_TAG} AS uv


# Includes all labels and timezone info to extend from
FROM docker.io/python:${PYTHON_IMG_TAG}-slim-bookworm AS base
ARG APP_VERSION
ARG COMMIT_REF
ARG PYTHON_IMG_TAG
LABEL org.hotosm.fmtm.app-name="fmtm-splitter" \
      org.hotosm.fmtm.app-version="${APP_VERSION}" \
      org.hotosm.fmtm.git-commit-ref="${COMMIT_REF:-none}" \
      org.hotosm.fmtm.python-img-tag="${PYTHON_IMG_TAG}" \
      org.hotosm.fmtm.maintainer="sysadmin@hotosm.org" \
      org.hotosm.fmtm.api-port="8000"
RUN apt-get update --quiet \
    && DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --quiet --no-install-recommends \
        "locales" "ca-certificates" \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates
# Set locale & env vars
RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen
# - Silence uv complaining about not being able to use hard links,
# - tell uv to byte-compile packages for faster application startups,
# - prevent uv from accidentally downloading isolated Python builds,
# - use a temp dir instead of cache during install,
# - select system python version,
# - declare `/opt/python` as the target for `uv sync` (i.e. instead of .venv).
ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1 \
    UV_PYTHON="python$PYTHON_IMG_TAG" \
    UV_PROJECT_ENVIRONMENT=/opt/python
STOPSIGNAL SIGINT


# Build stage will all dependencies required to build Python wheels
FROM base AS build
ARG API
RUN apt-get update --quiet \
    && DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --quiet --no-install-recommends \
        "build-essential" \
        "gcc" \
        "libpq-dev" \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock /_lock/
# Ensure caching & install with or without api dependencies
# FIXME add --locked & --no-dev flag to uv sync below
RUN --mount=type=cache,target=/root/.cache <<EOT
    uv sync \
        --project /_lock \
        --no-dev \
    $(if [ -z "$API" ]; then \
        echo ""; \
    else \
        echo "--group api"; \
    fi)
EOT


# Run stage will minimal dependencies required to run Python libraries
FROM base AS runtime
ARG PYTHON_IMG_TAG
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/opt/python/bin:$PATH" \
    PYTHONPATH="/opt" \
    PYTHON_LIB="/opt/python/lib/python$PYTHON_IMG_TAG/site-packages" \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
RUN apt-get update --quiet \
    && DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --quiet --no-install-recommends \
        "nano" \
        "curl" \
        "mime-support" \
        "postgresql-client" \
    && rm -rf /var/lib/apt/lists/*
COPY entrypoint.sh /container-entrypoint.sh
ENTRYPOINT ["/container-entrypoint.sh"]
WORKDIR /opt
# Copy Python deps from build to runtime
COPY --from=build /opt/python /opt/python
# Add non-root user, permissions
RUN useradd -u 1001 -m -c "user account" -d /home/appuser -s /bin/false appuser \
    && chown -R appuser:appuser /opt /home/appuser \
    && chmod +x /container-entrypoint.sh


# Stage to use during local development
FROM runtime AS debug
ARG API
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock /_lock/
RUN --mount=type=cache,target=/root/.cache <<EOT
    uv sync \
        --project /_lock \
        --group debug \
        --group test \
        --group docs \
        --group dev \
    $(if [ -z "$API" ]; then \
        echo ""; \
    else \
        echo "--group api"; \
    fi)
EOT


# Used during CI workflows (as root), with docs/test dependencies pre-installed
FROM debug AS ci
# Override entrypoint, as not possible in Github action
ENTRYPOINT [""]
CMD [""]


# Override CMD for API debug
FROM debug AS api-debug
# Add API code & fmtm-splitter module
COPY api/ /opt/api/
COPY fmtm_splitter/ /opt/python/lib/python3.12/site-packages/fmtm_splitter/
CMD ["python", "-Xfrozen_modules=off", "-m", "debugpy", \
    "--listen", "0.0.0.0:5678", "-m", "uvicorn", "api.main:app", \
    "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
    "--reload", "--log-level", "critical", "--no-access-log"]


# Final stage used during API deployment
FROM runtime AS api-prod
# Add API code & fmtm-splitter module
COPY api/ /opt/api/
COPY fmtm_splitter/ /opt/python/lib/python3.12/site-packages/fmtm_splitter/
# Change to non-root user
USER appuser
# Sanity check to see if build succeeded
RUN python -V \
    && python -Im site \
    && python -c 'import api.main'
# Note: 1 worker (process) per container, behind load balancer
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", \
    "--workers", "1", "--log-level", "critical", "--no-access-log"]


# Final stage to distribute fmtm-splitter in a container
FROM api-prod AS prod
# Change to non-root user
CMD ["bash"]
