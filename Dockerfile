# Copyright (c) 2022, 2023 Humanitarian OpenStreetMap Team
# This file is part of fmtm-splitter.
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with fmtm-splitter.  If not, see <https:#www.gnu.org/licenses/>.
#
ARG PYTHON_IMG_TAG=3.10


FROM docker.io/python:${PYTHON_IMG_TAG}-slim-bookworm AS base
ARG COMMIT_REF
ARG PYTHON_IMG_TAG
ARG MAINTAINER=admin@hotosm.org
LABEL org.hotosm.fmtm-splitter.python-img-tag="${PYTHON_IMG_TAG}" \
      org.hotosm.fmtm-splitter.commit-ref="${COMMIT_REF}" \
      org.hotosm.fmtm-splitter.maintainer="${MAINTAINER}"
RUN set -ex \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install \
    -y --no-install-recommends "locales" "ca-certificates" \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates
# Set locale
RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8



FROM base AS extract-deps
WORKDIR /opt/python
COPY pyproject.toml pdm.lock /opt/python/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir pdm==2.6.1
RUN pdm export --prod > requirements.txt \
    && pdm export -G debug -G test -G docs \
        --no-default > requirements-ci.txt



FROM base AS build-wheel
WORKDIR /build
COPY . .
RUN pip install pdm==2.6.1 \
    && pdm build



FROM base AS build
WORKDIR /opt/python
RUN set -ex \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install \
    -y --no-install-recommends \
        "build-essential" \
        "gcc" \
        "libpcre3-dev" \
        "libpq-dev" \
        "libspatialindex-dev" \
        "libproj-dev" \
        "libgeos-dev" \
    && rm -rf /var/lib/apt/lists/*
COPY --from=extract-deps \
    /opt/python/requirements.txt /opt/python/
RUN pip install --user --no-warn-script-location \
    --no-cache-dir -r ./requirements.txt
COPY --from=build-wheel \
    "/build/dist/*-py3-none-any.whl" .
RUN whl_file=$(find . -name '*-py3-none-any.whl' -type f) \
    && pip install --user --no-warn-script-location \
    --no-cache-dir "${whl_file}"



FROM base AS runtime
ARG PYTHON_IMG_TAG
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/root/.local/bin:$PATH" \
    PYTHON_LIB="/usr/local/lib/python$PYTHON_IMG_TAG/site-packages" \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
RUN set -ex \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install \
    -y --no-install-recommends \
        "nano" \
        "curl" \
        "libpcre3" \
        "postgresql-client" \
        "libglib2.0-0" \
        "libspatialindex-c6" \
        "libproj25" \
        "libgeos-c1v5" \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build \
    /root/.local \
    /root/.local
WORKDIR /data
COPY entrypoint.sh /container-entrypoint.sh



FROM runtime AS ci
ARG PYTHON_IMG_TAG
COPY --from=extract-deps \
    /opt/python/requirements-ci.txt /opt/python/
RUN cp -r /root/.local/bin/* /usr/local/bin/ \
    && cp -r /root/.local/lib/python${PYTHON_IMG_TAG}/site-packages/* \
    /usr/local/lib/python${PYTHON_IMG_TAG}/site-packages/ \
    && set -ex \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install \
    -y --no-install-recommends \
        "git" \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade --no-warn-script-location \
    --no-cache-dir -r \
    /opt/python/requirements-ci.txt \
    && rm -r /opt/python && rm -r /root/.local \
    # Pre-compile packages to .pyc (init speed gains)
    && python -c "import compileall; compileall.compile_path(maxlevels=10, quiet=1)"
# Override entrypoint, as not possible in Github action
ENTRYPOINT [""]
CMD [""]



FROM runtime AS prod
# Pre-compile packages to .pyc (init speed gains)
RUN python -c "import compileall; compileall.compile_path(maxlevels=10, quiet=1)" \
    && chmod +x /container-entrypoint.sh
ENTRYPOINT ["/container-entrypoint.sh"]
CMD ["bash"]
