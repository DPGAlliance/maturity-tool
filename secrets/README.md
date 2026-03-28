Create these files on the deployment host (not committed):

- `secrets/api_key`         (used by the API; maps to `API_KEY_FILE`)
- `secrets/github_token`    (used by viewer/refresh; maps to `GITHUB_TOKEN_FILE`)

Optional (only needed if you run summarization jobs):
- `secrets/openai_api_key`  (maps to `OPENAI_API_KEY_FILE`)

Docker Compose mounts these files into containers under `/run/secrets/*`:
- `secrets/api_key`        -> `/run/secrets/api_key`
- `secrets/github_token`   -> `/run/secrets/github_token`
- `secrets/openai_api_key` -> `/run/secrets/openai_api_key`

The code reads secrets via either:
- env var (e.g. `API_KEY`)
- or file var (e.g. `API_KEY_FILE=/run/secrets/api_key`)

Each file should contain just the secret value (no quotes, no trailing spaces ideally).

Security note: keep this folder readable only by the deployment user (e.g. `chmod -R go-rwx secrets`).
