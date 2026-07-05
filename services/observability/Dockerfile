FROM --platform=$BUILDPLATFORM golang:1.26-trixie AS build
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
COPY . .
RUN go mod download
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -trimpath -ldflags="-s -w" -o /out/autostream-observability ./cmd/observability

FROM gcr.io/distroless/base-debian13
COPY --from=build /out/autostream-observability /usr/local/bin/autostream-observability
COPY --from=build /out/autostream-observability /usr/local/bin/observability
ENV AUTOSTREAM_NODE_CONFIG=/etc/autostream-node/config.yml
USER nonroot:nonroot
ENTRYPOINT ["/usr/local/bin/autostream-observability"]
