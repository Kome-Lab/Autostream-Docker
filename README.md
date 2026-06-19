# AutoStream Dockerfiles

This repository stores Dockerfiles for AutoStream runtime services.

## Services

- `services/control-panel/Dockerfile`
- `services/discord-bot/Dockerfile`
- `services/encoder-recorder/Dockerfile`
- `services/observability/Dockerfile`
- `services/worker/Dockerfile`

## Publish Images

The GitHub Actions workflow in `.github/workflows/publish-ghcr.yml` builds all service images from matching source repository tags and publishes them to GHCR.

Image names:

- `ghcr.io/<owner>/autostream-docker/control-panel:<version>`
- `ghcr.io/<owner>/autostream-docker/discord-bot:<version>`
- `ghcr.io/<owner>/autostream-docker/encoder-recorder:<version>`
- `ghcr.io/<owner>/autostream-docker/observability:<version>`
- `ghcr.io/<owner>/autostream-docker/worker:<version>`

For a stable `vX.Y.Z` tag, the workflow also publishes `latest`.

Manual dry-run:

```bash
gh workflow run publish-ghcr.yml -f version=v1.2.3 -f source_owner=<owner> -f push_images=false
```

Manual publish:

```bash
gh workflow run publish-ghcr.yml -f version=v1.2.3 -f source_owner=<owner> -f push_images=true
```

If the source repositories are private, set `AUTOSTREAM_SOURCE_TOKEN` in this repository. Do not put provider secrets or runtime `.env` values in this repository.
