# syntax=docker/dockerfile:1

# Build Caddy from source with a selectable plugin set.
#
# Targets:
#   binary  - scratch image that carries only /caddy
#   runtime - Alpine image that runs as a container
#
# Build args:
#   CADDY_VERSION   upstream version, e.g. 2.11.9 or latest (default: latest)
#   WITH_*          true/false per plugin
#   LIBDNS_HUAWEICLOUD_FORK
#                   optional github.com/<owner>/<repo>@<commit> replacement for
#                   github.com/libdns/huaweicloud

ARG REGISTRY_MIRROR=docker.io

FROM ${REGISTRY_MIRROR}/library/golang:1.26-alpine AS builder

ARG TARGETARCH
ARG XCADDY_VERSION=v0.4.7
ARG CADDY_VERSION=latest
ARG GOPROXY=https://proxy.golang.org,direct
ARG WITH_CLOUDFLARE=false
ARG WITH_DNSPOD=false
ARG WITH_ALIDNS=false
ARG WITH_HUAWEICLOUD=false
ARG WITH_TROJAN=false
ARG WITH_CACHE=false
ARG WITH_S3_STORAGE=false
ARG LIBDNS_HUAWEICLOUD_FORK=
# The tagged releases of caddy-dns/dnspod still depend on libdns v0.2 and do
# not compile against libdns v1, which Caddy 2.11 uses. Pin the commit that
# migrated to libdns v1 until a tag exists.
ARG DNSPOD_VERSION=fb7cc31cc04c68a304b8d2672c3e5d9f2ad3d7ba

ENV GOPROXY=${GOPROXY} \
    GOOS=linux \
    GOARCH=${TARGETARCH} \
    CGO_ENABLED=0 \
    GOTOOLCHAIN=auto

RUN apk add --no-cache git ca-certificates

RUN go install github.com/caddyserver/xcaddy/cmd/xcaddy@${XCADDY_VERSION}

WORKDIR /build

RUN set -eu; \
    PLUGINS=""; \
    REPLACES=""; \
    if [ "$WITH_HUAWEICLOUD" = "true" ]; then \
        PLUGINS="$PLUGINS --with github.com/caddy-dns/huaweicloud"; \
        if [ -n "$LIBDNS_HUAWEICLOUD_FORK" ]; then \
            REPLACES="$REPLACES --replace github.com/libdns/huaweicloud=$LIBDNS_HUAWEICLOUD_FORK"; \
        fi; \
    fi; \
    if [ "$WITH_CLOUDFLARE" = "true" ]; then \
        PLUGINS="$PLUGINS --with github.com/caddy-dns/cloudflare"; \
    fi; \
    if [ "$WITH_DNSPOD" = "true" ]; then \
        PLUGINS="$PLUGINS --with github.com/caddy-dns/dnspod@$DNSPOD_VERSION"; \
    fi; \
    if [ "$WITH_ALIDNS" = "true" ]; then \
        PLUGINS="$PLUGINS --with github.com/caddy-dns/alidns"; \
    fi; \
    if [ "$WITH_CACHE" = "true" ]; then \
        PLUGINS="$PLUGINS --with github.com/caddyserver/cache-handler"; \
    fi; \
    if [ "$WITH_S3_STORAGE" = "true" ]; then \
        PLUGINS="$PLUGINS --with github.com/techknowlogick/certmagic-s3"; \
    fi; \
    if [ "$WITH_TROJAN" = "true" ]; then \
        PLUGINS="$PLUGINS --with github.com/imgk/caddy-trojan"; \
    fi; \
    case "$CADDY_VERSION" in \
        ""|latest) TAG="latest" ;; \
        v*) TAG="$CADDY_VERSION" ;; \
        *) TAG="v$CADDY_VERSION" ;; \
    esac; \
    echo "Caddy $TAG ${TARGETARCH}: $PLUGINS"; \
    xcaddy build "$TAG" --output /build/caddy $PLUGINS $REPLACES; \
    /build/caddy version

FROM scratch AS binary
ARG CADDY_VERSION=unknown
COPY --from=builder /build/caddy /caddy
LABEL org.opencontainers.image.title="Caddy with plugins" \
      org.opencontainers.image.version="${CADDY_VERSION}" \
      org.opencontainers.image.source="https://github.com/Oaklight/caddy-plugins"
ENTRYPOINT ["/caddy"]

FROM ${REGISTRY_MIRROR}/library/alpine:3.22 AS runtime
ARG CADDY_VERSION=unknown
RUN apk add --no-cache ca-certificates tzdata && \
    addgroup -g 1000 caddy && \
    adduser -D -u 1000 -G caddy caddy && \
    mkdir -p /etc/caddy /var/lib/caddy /var/log/caddy && \
    chown -R caddy:caddy /etc/caddy /var/lib/caddy /var/log/caddy
COPY --from=builder /build/caddy /usr/bin/caddy
LABEL org.opencontainers.image.title="Caddy with plugins" \
      org.opencontainers.image.version="${CADDY_VERSION}" \
      org.opencontainers.image.source="https://github.com/Oaklight/caddy-plugins"
USER caddy
EXPOSE 80 443 443/udp
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["caddy", "version"]
ENTRYPOINT ["caddy"]
CMD ["run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
