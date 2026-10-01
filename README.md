# Transcription Platform Monorepo

Микросервисная система транскрибации телефонных разговоров для внутреннего кабинета.

## Реализовано

- Архитектурная документация: допущения, C1/C2, границы микросервисов, API-контракты, модель данных, sequence, ADR.
- Frontend (Nuxt 3 SPA):
  - `/login`
  - `/`
  - `/upload` (drag-and-drop, множественная загрузка, прогресс, retry, abort)
  - `/calls` (список со статусами и пагинацией)
  - `/calls/:id` (карточка, аудио, транскрипт, jump to segment, edit segment, retry, delete)
  - `/profile` (смена пароля)
  - `/admin/users` (только ADMIN)
- Auth-service:
  - login, refresh, logout, me, password change
  - admin users list/create/update
  - роли USER/ADMIN
  - Argon2id для паролей
  - хранение хэша refresh token
- Upload-service:
  - init presigned URL
  - complete (проверка объекта, создание звонка в call-service, публикация SUBMIT в YMQ)
  - abort
- Call-service:
  - public API (list/get/delete/retry/audio-url/transcript/segment patch)
  - internal API для orchestration worker
  - статусы UPLOADING/QUEUED/PROCESSING/COMPLETED/FAILED
- Transcription-service:
  - долгоживущий consumer YMQ
  - обработка SUBMIT/CHECK_RESULT
  - запуск SpeechKit async operation
  - polling operation status
  - нормализация и сохранение транскрипции
  - защита от повторной доставки на уровне job state
- Infra:
  - Nginx API gateway
  - docker-compose
  - Dockerfile для каждого сервиса
  - health endpoints `/health/live` и `/health/ready`

## Что осталось до production-ready

- Жесткая валидация фактических форматов SpeechKit по вашей целевой модели (проверить и зафиксировать официальные ограничения).
- Интеграция выдачи IAM-token из Lockbox/metadata вместо статического `YC_IAM_TOKEN`.
- Более строгая идемпотентность (dedup таблица message_id в call-service).
- Нормализация временных меток SpeechKit под точный формат ответа вашей версии API.
- Нагрузочные тесты и настройка retry/backoff/dead-letter queue.
- Полноценные Alembic миграции в CI/CD pipeline (сейчас есть стартовые ревизии).

## Команды сборки

```bash
docker compose build
```

## Команды запуска

```bash
cp .env.example .env
# заполнить значения
docker compose up -d
docker compose logs -f
```

Gateway: `http://localhost:8080`

## Переменные окружения

Сводный пример: `.env.example`

Критичные переменные:
- `AUTH_DATABASE_URL`
- `CALLS_DATABASE_URL`
- `JWT_SECRET`
- `UPLOAD_SIGNING_SECRET`
- `YC_S3_*`
- `YMQ_*`
- `CALL_SERVICE_INTERNAL_API_KEY`
- `YC_IAM_TOKEN_SOURCE` (`auto` или `env`)
- `YC_IAM_TOKEN` (только если `YC_IAM_TOKEN_SOURCE=env`)
- `YC_METADATA_TOKEN_URL` (для `auto` режима)
- `SPEECHKIT_LONG_RUNNING_URL`
- `SPEECHKIT_OPERATION_URL`

## Порядок развёртывания на Yandex Compute Cloud

1. Создать/проверить внешние ресурсы: Managed PostgreSQL, Object Storage bucket, Message Queue, SpeechKit доступ, Lockbox secret, Container Registry.
2. На VM установить Docker и Docker Compose.
3. Забрать репозиторий на VM.
4. Подгрузить секреты из Lockbox:

```bash
eval "$(infra/scripts/load_lockbox_env.sh)"
```

5. Сформировать `.env` (либо экспортировать env в systemd shell).
6. Выполнить миграции (из контейнеров сервисов или отдельным job):
   - `auth-service` alembic upgrade head
   - `call-service` alembic upgrade head
7. Запустить:

```bash
docker compose up -d --build
```

8. Проверить health endpoints сервисов через gateway/внутренние порты.
9. Создать первого admin пользователя: задайте `AUTH_BOOTSTRAP_ADMIN_PASSWORD` в `.env` перед первым запуском (или создайте через SQL/API).

## Автозапуск после reboot (systemd)

1. Создать файл окружения:

```bash
sudo tee /etc/default/transcription-platform >/dev/null <<'EOF'
LOCKBOX_SECRET_ID=e6q81sss0i3lf889lvt8
YC_METADATA_TOKEN_URL=http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token
TARGET_ENV_FILE=/home/evponomarev1985/transcription-platform/.env
EOF
```

2. Установить unit:

```bash
sudo cp /home/evponomarev1985/transcription-platform/infra/systemd/transcription-platform.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable transcription-platform
sudo systemctl start transcription-platform
```

3. Проверить:

```bash
systemctl status transcription-platform --no-pager
docker compose -f /home/evponomarev1985/transcription-platform/docker-compose.yml ps
```

## Документация

- Архитектура и контракты: `docs/architecture.md`
- ADR размещения frontend: `docs/adr/ADR-001-nuxt-deployment.md`

## CI/CD (GitHub Actions)

- CI workflow: `.github/workflows/ci.yml`
  - frontend build (`npm ci && npm run build`)
  - Python compile checks for `auth-service`, `call-service`, `transcription-service`
- Deploy workflow: `.github/workflows/deploy.yml`
  - trigger: push to `main` or manual run
  - sync code to VM by rsync
  - build containers, run Alembic migrations, recreate stack

Required GitHub repository secrets are listed in `.github/README-secrets.md`.
