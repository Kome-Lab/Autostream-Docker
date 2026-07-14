FROM --platform=$BUILDPLATFORM golang:1.26.5-trixie AS build
ARG TARGETOS
ARG TARGETARCH
ARG VERSION=dev
ARG COMMIT=unknown
ARG BUILD_DATE=unknown
WORKDIR /src
COPY . .
RUN go mod download
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -trimpath -ldflags="-s -w -X github.com/example/autostream-observability/internal/version.Version=${VERSION} -X github.com/example/autostream-observability/internal/version.Commit=${COMMIT} -X github.com/example/autostream-observability/internal/version.BuildDate=${BUILD_DATE}" -o /out/autostream-observability ./cmd/observability

FROM gcr.io/distroless/base-debian13
COPY --from=build /out/autostream-observability /usr/local/bin/autostream-observability
COPY --from=build /out/autostream-observability /usr/local/bin/observability
ENV AUTOSTREAM_NODE_CONFIG=/etc/autostream-observability/config.yml
USER nonroot:nonroot
ENTRYPOINT ["/usr/local/bin/autostream-observability"]
