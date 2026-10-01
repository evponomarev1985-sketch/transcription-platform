# GitHub Actions secrets for deploy

Set these repository secrets in GitHub before running deploy workflow:

- `DEPLOY_HOST` — production VM host (example: `62.84.114.2`)
- `DEPLOY_USER` — SSH user (example: `evponomarev1985`)
- `DEPLOY_PATH` — absolute path to project on VM (example: `/home/evponomarev1985/transcription-platform`)
- `DEPLOY_SSH_PRIVATE_KEY` — private SSH key content for deploy user
- `GHCR_USERNAME` — GitHub username that can pull from GHCR (example: `evponomarev1985-sketch`)
- `GHCR_READ_TOKEN` — GitHub token with package read access for GHCR pull on VM

The deploy workflow now builds images in GitHub Actions and pushes to GHCR using tags based on commit SHA.
VM pulls these images (no local docker build on VM).

Image naming format in GHCR:

- `ghcr.io/<owner>/transcription-platform-api-gateway:<sha>`
- `ghcr.io/<owner>/transcription-platform-frontend:<sha>`
- `ghcr.io/<owner>/transcription-platform-auth-service:<sha>`
- `ghcr.io/<owner>/transcription-platform-upload-service:<sha>`
- `ghcr.io/<owner>/transcription-platform-call-service:<sha>`
- `ghcr.io/<owner>/transcription-platform-transcription-service:<sha>`

Notes:

- Deploy workflow uses `rsync --delete`, so target directory must contain only this project.
- Server must already have valid `${DEPLOY_PATH}/.env` and Docker/Compose installed.
- Deploy runs Alembic migrations for `auth-service` and `call-service` before `up -d`.
