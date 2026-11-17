# Local helper. CI is authoritative: .github/workflows/build.yml

IMAGE ?= oaklight/caddy
CADDY_VERSION ?= latest
VARIANT ?= default

ifeq ($(VARIANT),default)
  SUFFIX := huaweicloud-cache-s3
  PLUGINS := --build-arg WITH_HUAWEICLOUD=true --build-arg WITH_CACHE=true --build-arg WITH_S3_STORAGE=true
else ifeq ($(VARIANT),full)
  SUFFIX := huaweicloud-cloudflare-dnspod-alidns-cache-s3-trojan
  PLUGINS := --build-arg WITH_HUAWEICLOUD=true --build-arg WITH_CLOUDFLARE=true \
             --build-arg WITH_DNSPOD=true --build-arg WITH_ALIDNS=true \
             --build-arg WITH_CACHE=true --build-arg WITH_S3_STORAGE=true \
             --build-arg WITH_TROJAN=true
else
  $(error VARIANT must be default or full)
endif

.PHONY: help build build-full version

help:
	@echo "make build [VARIANT=default|full] [CADDY_VERSION=2.11.9]"
	@echo "make version   print the resolved tag suffix"

version:
	@echo "$(IMAGE):v$(CADDY_VERSION)-$(SUFFIX)"

build:
	docker build \
	  --target runtime \
	  --build-arg CADDY_VERSION=$(CADDY_VERSION) \
	  $(PLUGINS) \
	  -t "$(IMAGE):local-$(SUFFIX)" .

build-full:
	$(MAKE) build VARIANT=full
