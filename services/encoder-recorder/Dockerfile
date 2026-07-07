FROM --platform=$BUILDPLATFORM golang:1.26-trixie AS build
ARG TARGETOS
ARG TARGETARCH
ARG VERSION=dev
ARG COMMIT=unknown
ARG BUILD_DATE=unknown
WORKDIR /src
COPY . .
RUN go mod download
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -trimpath -ldflags="-s -w -X github.com/example/autostream-encoder-recorder/internal/version.Version=${VERSION} -X github.com/example/autostream-encoder-recorder/internal/version.Commit=${COMMIT} -X github.com/example/autostream-encoder-recorder/internal/version.BuildDate=${BUILD_DATE}" -o /out/autostream-encoder-recorder ./cmd/encoder-recorder

FROM debian:trixie-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 65532 --home-dir /var/lib/autostream autostream \
    && mkdir -p /var/lib/autostream/encoder-recorder /var/lib/autostream/archives \
    && chown -R 65532:65532 /var/lib/autostream
COPY --from=build /out/autostream-encoder-recorder /usr/local/bin/autostream-encoder-recorder
COPY --from=build /out/autostream-encoder-recorder /usr/local/bin/encoder-recorder
ENV AUTOSTREAM_NODE_CONFIG=/etc/autostream-node/config.yml
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/autostream-encoder-recorder"]
