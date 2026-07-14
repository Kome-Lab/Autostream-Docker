FROM --platform=$BUILDPLATFORM golang:1.26.5-trixie AS build
ARG TARGETOS
ARG TARGETARCH
ARG VERSION=dev
ARG COMMIT=unknown
ARG BUILD_DATE=unknown
WORKDIR /src
COPY . .
RUN go mod download
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -trimpath -ldflags="-s -w -X github.com/example/autostream-discord-bot/internal/version.Version=${VERSION} -X github.com/example/autostream-discord-bot/internal/version.Commit=${COMMIT} -X github.com/example/autostream-discord-bot/internal/version.BuildDate=${BUILD_DATE}" -o /out/autostream-discord-bot ./cmd/discord-bot

FROM gcr.io/distroless/base-debian13
COPY --from=build /out/autostream-discord-bot /usr/local/bin/autostream-discord-bot
COPY --from=build /out/autostream-discord-bot /usr/local/bin/discord-bot
ENV AUTOSTREAM_NODE_CONFIG=/etc/autostream-discord-bot/config.yml
USER nonroot:nonroot
ENTRYPOINT ["/usr/local/bin/autostream-discord-bot"]
