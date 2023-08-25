#!/bin/bash

set -eo pipefail

PKG_VERSION=0.1.0

docker build . \
    -t "ghcr.io/hotosm/fmtm-splitter:${PKG_VERSION}" \
    --target prod \
    --build-arg PKG_VERSION="${PKG_VERSION}"

docker push "ghcr.io/hotosm/fmtm-splitter:${PKG_VERSION}"

docker build . --push \
    -t ghcr.io/hotosm/fmtm-splitter:ci \
    --target ci \
    --build-arg PKG_VERSION="${PKG_VERSION}"

docker push ghcr.io/hotosm/fmtm-splitter:ci
