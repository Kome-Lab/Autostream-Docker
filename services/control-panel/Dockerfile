FROM node:26-alpine AS web
WORKDIR /src
COPY web/package*.json ./web/
RUN cd web && npm ci --no-audit --no-fund
COPY . .
RUN cd web && npm run build

FROM --platform=$BUILDPLATFORM golang:1.26-trixie AS build
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
COPY . .
RUN go mod download
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -trimpath -ldflags="-s -w" -o /out/control-panel ./cmd/control-panel

FROM gcr.io/distroless/base-debian13
COPY --from=build /out/control-panel /usr/local/bin/control-panel
COPY --from=web /src/web/out /usr/share/autostream-control-panel
ENV AUTOSTREAM_WEB_DIR=/usr/share/autostream-control-panel
USER nonroot:nonroot
ENTRYPOINT ["/usr/local/bin/control-panel"]
