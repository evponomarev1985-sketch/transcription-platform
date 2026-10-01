# GitHub Actions secrets for deploy

Set these repository secrets in GitHub before running deploy workflow:

- `DEPLOY_HOST` — production VM host (example: `62.84.114.2`)
- `DEPLOY_USER` — SSH user (example: `evponomarev1985`)
- `DEPLOY_PATH` — absolute path to project on VM (example: `/home/evponomarev1985/transcription-platform`)
- `DEPLOY_SSH_PRIVATE_KEY` — private SSH key content for deploy user

Notes:

- Deploy workflow uses `rsync --delete`, so target directory must contain only this project.
- Server must already have valid `${DEPLOY_PATH}/.env` and Docker/Compose installed.
- Deploy runs Alembic migrations for `auth-service` and `call-service` before `up -d`.
