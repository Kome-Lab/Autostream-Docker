FROM --platform=$BUILDPLATFORM golang:1.26-trixie AS build
ARG TARGETOS
ARG TARGETARCH
ARG VERSION=dev
ARG COMMIT=unknown
ARG BUILD_DATE=unknown
WORKDIR /src
COPY . .
RUN go mod download
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -trimpath -ldflags="-s -w -X github.com/example/autostream-worker/internal/version.Version=${VERSION} -X github.com/example/autostream-worker/internal/version.Commit=${COMMIT} -X github.com/example/autostream-worker/internal/version.BuildDate=${BUILD_DATE}" -o /out/autostream-worker ./cmd/worker

FROM gcr.io/distroless/base-debian13
COPY --from=build /out/autostream-worker /usr/local/bin/autostream-worker
COPY --from=build /out/autostream-worker /usr/local/bin/worker
ENV AUTOSTREAM_NODE_CONFIG=/etc/autostream-worker/config.yml
USER nonroot:nonroot
ENTRYPOINT ["/usr/local/bin/autostream-worker"]
