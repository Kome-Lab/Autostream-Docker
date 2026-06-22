FROM --platform=$BUILDPLATFORM golang:1.26-trixie AS build
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
COPY . .
RUN go mod download
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -trimpath -ldflags="-s -w" -o /out/discord-bot ./cmd/discord-bot

FROM gcr.io/distroless/base-debian13
COPY --from=build /out/discord-bot /usr/local/bin/discord-bot
USER nonroot:nonroot
ENTRYPOINT ["/usr/local/bin/discord-bot"]
