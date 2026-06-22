FROM --platform=$BUILDPLATFORM golang:1.26-trixie AS build
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
COPY . .
RUN go mod download
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -trimpath -ldflags="-s -w" -o /out/observability ./cmd/observability

FROM gcr.io/distroless/base-debian13
COPY --from=build /out/observability /usr/local/bin/observability
USER nonroot:nonroot
ENTRYPOINT ["/usr/local/bin/observability"]
