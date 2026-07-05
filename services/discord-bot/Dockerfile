FROM --platform=$BUILDPLATFORM golang:1.26-trixie AS build
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
COPY . .
RUN go mod download
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -trimpath -ldflags="-s -w" -o /out/autostream-discord-bot ./cmd/discord-bot

FROM gcr.io/distroless/base-debian13
COPY --from=build /out/autostream-discord-bot /usr/local/bin/autostream-discord-bot
COPY --from=build /out/autostream-discord-bot /usr/local/bin/discord-bot
ENV AUTOSTREAM_NODE_CONFIG=/etc/autostream-node/config.yml
USER nonroot:nonroot
ENTRYPOINT ["/usr/local/bin/autostream-discord-bot"]
