FROM --platform=$BUILDPLATFORM golang:1.26.5-trixie AS build
ARG TARGETOS
ARG TARGETARCH
ARG VERSION=dev
ARG COMMIT=unknown
ARG BUILD_DATE=unknown
WORKDIR /src
COPY . .
RUN go mod download
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -trimpath -ldflags="-s -w -X github.com/example/autostream-worker/internal/version.Version=${VERSION} -X github.com/example/autostream-worker/internal/version.Commit=${COMMIT} -X github.com/example/autostream-worker/internal/version.BuildDate=${BUILD_DATE}" -o /out/autostream-worker ./cmd/worker

FROM debian:trixie-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates fontconfig fonts-noto-cjk \
    && test -r /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc \
    && install -d -m 0750 -o 65532 -g 65532 /var/lib/autostream/worker \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/autostream-worker /usr/local/bin/autostream-worker
COPY --from=build /out/autostream-worker /usr/local/bin/worker
ENV AUTOSTREAM_NODE_CONFIG=/etc/autostream-worker/config.yml
ENV AUTOSTREAM_SCENE_FONT_FILE=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/autostream-worker"]
