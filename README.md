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

| Variant | Plugins | Descriptive tag | Short alias |
| --- | --- | --- | --- |
| `default` | huaweicloud, cache, s3-storage | `v{version}-huaweicloud-cache-s3` | `v{version}-default` |
| `full` | all seven | `v{version}-huaweicloud-cloudflare-dnspod-alidns-cache-s3-trojan` | `v{version}-full` |

Each tag exists twice: the binary image uses the tag as listed, the runtime
image appends `-alpine`. The descriptive tag and the short alias point at the
same image, so both naming schemes stay valid.

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
5. Verifies every variant before the run passes:
   - `caddy version` reports the expected upstream version.
   - `caddy list-modules --packages` contains every expected plugin.
   - The config validates with `caddy validate`.
   - The container serves a request on `:8080`.
   - The runtime image runs as uid 1000.

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

## Plugin version pins

`caddy-dns/dnspod` tagged releases (through `v0.0.4`) still depend on
`libdns` v0.2 and do not compile against `libdns` v1, which Caddy 2.11
requires. The build pins the commit that migrated to `libdns` v1 until a new
tag is published. Override it when that changes:

```bash
docker build --build-arg DNSPOD_VERSION=v0.1.0 --build-arg WITH_DNSPOD=true .
```

Verified locally with Caddy 2.11.9: the `default` and `full` variants build,
report the expected version, load every expected plugin, validate a config and
serve a request.

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
