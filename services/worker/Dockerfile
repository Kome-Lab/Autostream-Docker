FROM --platform=$BUILDPLATFORM golang:1.26-trixie AS build
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
COPY . .
RUN go mod download
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -trimpath -ldflags="-s -w" -o /out/autostream-worker ./cmd/worker

FROM gcr.io/distroless/base-debian13
COPY --from=build /out/autostream-worker /usr/local/bin/autostream-worker
COPY --from=build /out/autostream-worker /usr/local/bin/worker
ENV AUTOSTREAM_NODE_CONFIG=/etc/autostream-node/config.yml
USER nonroot:nonroot
ENTRYPOINT ["/usr/local/bin/autostream-worker"]
