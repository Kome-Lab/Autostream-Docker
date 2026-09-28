FROM golang:1.26.5-trixie AS build
ARG TARGETOS
ARG TARGETARCH
ARG VERSION=dev
ARG COMMIT=unknown
ARG BUILD_DATE=unknown
WORKDIR /src
# DAVE and Go must use the same native architecture on each matrix runner.
RUN test "${TARGETOS}/${TARGETARCH}" = "$(go env GOOS)/$(go env GOARCH)"
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates cmake ninja-build g++ make pkg-config autoconf automake \
    libtool zip unzip tar \
  && rm -rf /var/lib/apt/lists/*
COPY go.mod go.sum ./
COPY third_party ./third_party
RUN go mod download
COPY . .
# Docker contexts omit the parent .git directory, so recursive submodule gitdir
# pointers cannot serve vcpkg's versioned port lookup. Restore only the history
# reachable from the accepted vcpkg gitlink; do not resolve a branch or new pin.
RUN set -eu; \
  vcpkg_root="$PWD/third_party/discordgo/dave/libdave/cpp/vcpkg"; \
  vcpkg_commit=16c71a39e5a0fc0bdb3fad03beef8f38ee00ee3b; \
  git init --bare /tmp/vcpkg-history.git; \
  git --git-dir=/tmp/vcpkg-history.git fetch --no-tags --no-write-fetch-head \
    https://github.com/microsoft/vcpkg.git "$vcpkg_commit"; \
  git --git-dir=/tmp/vcpkg-history.git read-tree "$vcpkg_commit"; \
  git --git-dir=/tmp/vcpkg-history.git --work-tree="$vcpkg_root" \
    -c core.bare=false diff --exit-code "$vcpkg_commit" -- .; \
  rm -f "$vcpkg_root/.git"; \
  mv /tmp/vcpkg-history.git "$vcpkg_root/.git"
RUN make -C third_party/discordgo/dave/libdave/cpp BUILD_TYPE=Release
RUN set -eu; \
  libdave_build="$PWD/third_party/discordgo/dave/libdave/cpp/build"; \
  vcpkg_libdir="$(find "$libdave_build/vcpkg_installed" -maxdepth 2 -type d -name lib -print -quit)"; \
  test -n "$vcpkg_libdir"; \
  vcpkg_libs="$(find "$vcpkg_libdir" -maxdepth 1 -type f -name '*.a' -print | sort | tr '\n' ' ')"; \
  CGO_ENABLED=1 \
  CGO_CFLAGS="-I$PWD/third_party/discordgo/dave/libdave/cpp/includes" \
  CGO_LDFLAGS="-L$vcpkg_libdir $libdave_build/libdave.a -Wl,--start-group $vcpkg_libs -Wl,--end-group -lstdc++ -lm -ldl -lpthread" \
    go build -trimpath -o /out/autostream-discord-bot \
      -ldflags="-s -w -X github.com/example/autostream-discord-bot/internal/version.Version=${VERSION} -X github.com/example/autostream-discord-bot/internal/version.Commit=${COMMIT} -X github.com/example/autostream-discord-bot/internal/version.BuildDate=${BUILD_DATE}" \
      ./cmd/discord-bot

# The DAVE-linked binary also needs the trixie C++ runtime libraries.
FROM gcr.io/distroless/cc-debian13
COPY --from=build /out/autostream-discord-bot /usr/local/bin/autostream-discord-bot
COPY --from=build /out/autostream-discord-bot /usr/local/bin/discord-bot
ENV AUTOSTREAM_NODE_CONFIG=/etc/autostream-discord-bot/config.yml
USER nonroot:nonroot
ENTRYPOINT ["/usr/local/bin/autostream-discord-bot"]
