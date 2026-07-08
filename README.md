# AutoStream Dockerfiles

This repository stores Dockerfiles for AutoStream runtime services.

Runtime environment values are supplied by the deployment compose file, not by
these images. Only Control Panel and Observability require `DATABASE_URL`.
Encoder/Recorder, Worker, and Discord Bot do not have their own MariaDB
database; they receive runtime configuration from Control Panel.

Node services expect a Panel-generated Node Agent config mounted at
`/etc/autostream-<service>/config.yml` by default. Compose files may point
`AUTOSTREAM_NODE_CONFIG` at a service-specific read-only mount when multiple
nodes run on the same host. Service images run as nonroot, so bind-mounted
config files should be readable by container group `65532` and kept non-world
readable, for example `root:65532` with mode `0640`.

## Services

- `services/control-panel/Dockerfile`
- `services/discord-bot/Dockerfile`
- `services/encoder-recorder/Dockerfile`
- `services/observability/Dockerfile`
- `services/worker/Dockerfile`

## Publish Images

The GitHub Actions workflow in `.github/workflows/publish-ghcr.yml` builds all service images and publishes them to GHCR.
AutoStream services can have different source repository versions. The workflow resolves each service source tag in this order:

1. Matching workflow dispatch input such as `control_panel_version` or `worker_version`.
2. `source-versions.env` in this repository.
3. The Docker image `version` input or pushed tag.

Image names:

- `ghcr.io/<owner>/autostream-docker/control-panel:<version>`
- `ghcr.io/<owner>/autostream-docker/discord-bot:<version>`
- `ghcr.io/<owner>/autostream-docker/encoder-recorder:<version>`
- `ghcr.io/<owner>/autostream-docker/observability:<version>`
- `ghcr.io/<owner>/autostream-docker/worker:<version>`

Current default source tags are pinned in `source-versions.env`.

For a stable `vX.Y.Z` tag, the workflow also publishes `latest`.

Manual dry-run:

```bash
gh workflow run publish-ghcr.yml -f version=v1.3.0 -f source_owner=<owner> -f push_images=false
```

Manual dry-run with mixed service source versions:

```bash
gh workflow run publish-ghcr.yml \
  -f version=v1.3.0 \
  -f source_owner=<owner> \
  -f control_panel_version=v1.3.0 \
  -f discord_bot_version=v1.0.8 \
  -f encoder_recorder_version=v1.0.8 \
  -f observability_version=v1.0.10 \
  -f worker_version=v1.0.8 \
  -f push_images=false
```

Manual publish:

```bash
gh workflow run publish-ghcr.yml -f version=v1.3.0 -f source_owner=<owner> -f push_images=true
```

If the source repositories are private, set one of these repository secrets in `Autostream-Docker`:

- `AUTOSTREAM_SOURCE_TOKEN` with read access to the private source repositories.
- `GITHUBTOKEN` with read access to the private source repositories. This name is also used for GHCR login when present.

The built-in `GITHUB_TOKEN` is only enough when the source repositories are public or otherwise readable by the workflow. Do not put provider secrets or runtime `.env` values in this repository.
