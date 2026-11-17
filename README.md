# Caddy with plugins

Caddy compiled from source with a fixed plugin set, published to Docker Hub as
two image flavours: a `scratch` image that carries only the binary, and an
Alpine image that runs as a container. CI tracks upstream Caddy releases, so a
new Caddy version is built within a day of its release.

## Plugins

| Plugin | Build flag | Provides |
| --- | --- | --- |
| huaweicloud | `WITH_HUAWEICLOUD=true` | Huawei Cloud DNS provider |
| cloudflare | `WITH_CLOUDFLARE=true` | Cloudflare DNS provider |
| dnspod | `WITH_DNSPOD=true` | DNSPod DNS provider |
| alidns | `WITH_ALIDNS=true` | Alibaba Cloud DNS provider |
| cache | `WITH_CACHE=true` | Server-side HTTP cache (`cache-handler`) |
| s3-storage | `WITH_S3_STORAGE=true` | S3-compatible certificate storage (`certmagic-s3`) |
| trojan | `WITH_TROJAN=true` | Trojan proxy protocol |

## Variants and tags

`v{version}` is the upstream Caddy version, for example `v2.11.9`.

| Variant | Plugins | Tag (binary) | Tag (runtime) |
| --- | --- | --- | --- |
| `default` | huaweicloud, cache, s3-storage | `v{version}-huaweicloud-cache-s3` | `v{version}-huaweicloud-cache-s3-alpine` |
| `full` | all seven | `v{version}-huaweicloud-cloudflare-dnspod-alidns-cache-s3-trojan` | same, `-alpine` |

The `default` variant also updates `latest` and `latest-alpine`.

Both variants are multi-arch: `linux/amd64` and `linux/arm64`.

The binary image is a `scratch` image. Extract the binary from it:

```bash
docker create --name caddy-extract oaklight/caddy:v2.11.9-huaweicloud-cache-s3
docker cp caddy-extract:/caddy ./caddy
docker rm caddy-extract
```

## Run

```bash
docker run -d \
  --name caddy \
  -p 80:80 -p 443:443 -p 443:443/udp \
  -v /path/to/Caddyfile:/etc/caddy/Caddyfile \
  -v caddy_data:/var/lib/caddy \
  oaklight/caddy:v2.11.9-huaweicloud-cache-s3-alpine
```

## Server-side cache

```caddyfile
{
    cache {
        ttl 1h
        stale 24h
        default_cache_control public, max-age=3600
    }
}

example.com {
    cache
    reverse_proxy localhost:8080
}
```

## Shared certificate storage on S3

Any S3-compatible backend works: AWS S3, MinIO, Oracle Cloud Object Storage.
Several Caddy instances can share one bucket. The plugin takes a distributed
lock, so only one instance issues a given certificate.

```caddyfile
{
    storage s3 {
        endpoint "https://<endpoint>"
        bucket "caddy-certs"
        region "<region>"
        access_key "<access-key>"
        secret_key "<secret-key>"
        prefix "caddy"
        encryption_key "<32-byte-key>"
        use_path_style true
    }
}
```

Set `use_path_style true` for custom endpoints. The plugin comes from
[techknowlogick/certmagic-s3](https://github.com/techknowlogick/certmagic-s3).

## Build

### CI

`.github/workflows/build.yml` runs daily, on manual dispatch and on changes to
the build files. It does this:

1. Resolves the latest Caddy release, or the version given to the workflow.
2. Expands the variant list into a matrix of variant × target.
3. Skips any tag that already exists on Docker Hub.
4. Builds `linux/amd64` and `linux/arm64` and pushes.

Manual run with a pinned version and no push:

```bash
gh workflow run build.yml -f caddy_version=2.11.9 -f push=false
```

Required repository secrets: `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`.

### Local

```bash
make build                                   # default variant, latest Caddy
make build VARIANT=full CADDY_VERSION=2.11.9
make version                                 # print the resolved image tag
```

## Optional libdns replacement

`LIBDNS_HUAWEICLOUD_FORK` replaces `github.com/libdns/huaweicloud` at build
time with `xcaddy --replace`. Use it to test an upstream fix before it is
merged.

```bash
docker build --target runtime \
  --build-arg WITH_HUAWEICLOUD=true \
  --build-arg LIBDNS_HUAWEICLOUD_FORK=github.com/<owner>/<repo>@<commit> \
  -t caddy:test .
```
