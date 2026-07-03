FROM node:26-alpine AS web
WORKDIR /src
COPY web/package*.json ./web/
RUN cd web && npm ci --no-audit --no-fund
COPY . .
RUN cd web && npm run build \
    && if [ -d out ]; then cp -a out /tmp/autostream-control-panel-web; \
       elif [ -d dist ]; then cp -a dist /tmp/autostream-control-panel-web; \
       else echo "control-panel web build did not produce web/out or web/dist" >&2; exit 1; fi

FROM --platform=$BUILDPLATFORM golang:1.26-trixie AS build
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
COPY . .
RUN go mod download
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -trimpath -ldflags="-s -w" -o /out/control-panel ./cmd/control-panel

FROM gcr.io/distroless/base-debian13
COPY --from=build /out/control-panel /usr/local/bin/control-panel
COPY --from=web /tmp/autostream-control-panel-web /usr/share/autostream-control-panel
ENV AUTOSTREAM_WEB_DIR=/usr/share/autostream-control-panel
USER nonroot:nonroot
ENTRYPOINT ["/usr/local/bin/control-panel"]
