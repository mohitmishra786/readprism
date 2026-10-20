# ReadPrism all-in-one image (#208): API, three queue workers, beat and the web
# app in one container, supervised by s6-overlay. Pair it with Postgres and
# Redis for a 3-container install: docker compose -f compose.aio.yml up -d
#
# Build from the repository root:
#   docker build -f deploy/aio/Dockerfile -t readprism:aio .
# LITE=1 drops torch/sentence-transformers (hash embedder; ~1.8 GB smaller).

# --- web app (glibc build, so it runs on the Debian runtime below) ---------
FROM node:26-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --legacy-peer-deps
COPY frontend/ ./
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN npm run build

# --- runtime ---------------------------------------------------------------
FROM python:3.12-slim

ARG S6_OVERLAY_VERSION=3.2.0.2
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl xz-utils \
    && rm -rf /var/lib/apt/lists/* \
    && case "${TARGETARCH:-amd64}" in \
         amd64) S6_ARCH=x86_64 ;; arm64) S6_ARCH=aarch64 ;; *) echo "unsupported arch ${TARGETARCH}" >&2; exit 1 ;; \
       esac \
    && base="https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}" \
    && curl -fsSL "$base/s6-overlay-noarch.tar.xz" -o /tmp/noarch.tar.xz \
    && curl -fsSL "$base/s6-overlay-${S6_ARCH}.tar.xz" -o /tmp/arch.tar.xz \
    && tar -C / -Jxpf /tmp/noarch.tar.xz && tar -C / -Jxpf /tmp/arch.tar.xz \
    && rm /tmp/*.tar.xz

# Node runtime for the Next.js standalone server (same major as the build).
COPY --from=web /usr/local/bin/node /usr/local/bin/node

WORKDIR /app
COPY backend/requirements.txt backend/requirements-lite.txt ./
ARG LITE=0
RUN if [ "$LITE" = "1" ]; then REQ=requirements-lite.txt; else REQ=requirements.txt; fi \
    && pip install --no-cache-dir -r "$REQ"
RUN playwright install chromium --with-deps 2>/dev/null || true
COPY backend/ ./

COPY --from=web /web/.next/standalone /web
COPY --from=web /web/.next/static /web/.next/static
COPY --from=web /web/public /web/public

COPY deploy/aio/rootfs/ /
RUN chmod +x /etc/s6-overlay/scripts/* /usr/local/bin/aio-healthcheck \
    && find /etc/s6-overlay/s6-rc.d -name run -exec chmod +x {} +

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # A failed migration stops the container instead of serving a broken API.
    S6_BEHAVIOUR_IF_STAGE2_FAILS=2 \
    # Migrations on a big database can take a while.
    S6_CMD_WAIT_FOR_SERVICES_MAXTIME=0 \
    S6_KEEP_ENV=1

EXPOSE 8000 3000
HEALTHCHECK --interval=30s --timeout=10s --start-period=150s --retries=3 \
    CMD ["/usr/local/bin/aio-healthcheck"]
ENTRYPOINT ["/init"]
