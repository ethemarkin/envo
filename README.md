# Envo

A developer tool for teams to manage application configuration and secrets per project and environment.

| Directory | Contents |
| --- | --- |
| `backend/` | FastAPI + PostgreSQL API (SQLAlchemy 2, Alembic) |
| `frontend/` | React + TypeScript + Tailwind dashboard (Vite) |
| `cli/` | Go CLI (`envo`) |
| `examples/ci/` | CI/CD examples |

## Features

Accounts and access:

- Email/password sign-up (invitation only) and sign-in, HttpOnly cookie sessions, CSRF protection, rotating refresh tokens and signing out of all sessions
- GitLab-style nested groups with projects at any level; group and project memberships, roles inherited downwards, instance admin (the first user)
- Dashboard: group/project tree on the left, group and project pages, member management, settings and an admin panel

Configuration and secrets:

- All values are stored with AES-256-GCM envelope encryption: a data key per environment, a master key supplied from outside the database, and AAD bound to the environment and key name
- Visible and secret variables; reading, writing and exporting secret values follows role and protected-environment rules
- Server-side `.env` parsing, import with merge semantics (with a preview) and re-importable export
- An environment revision on every write, change history and concurrent-edit protection via `If-Match`; audit logs (never containing values)
- Environment editor: edit, reveal, save in bulk, `.env` import/export

CLI:

- `envo login` with sign-in approved in the browser (the code is shown in the terminal and entered on the web); tokens are kept in the OS keychain, or in a file with `0600` permissions if there is none
- `envo init`, `pull`, `push`, `set`, `run`, plus `logout` and `whoami`
- `envo run` passes values to the child process without writing them to disk, forwards signals and returns the exit code (tested on Windows and Linux)
- `ENVO_TOKEN` for CI

Team and CI access:

- Group or project invitations for emails without an account: a single-use link valid for 7 days that can only be accepted with the invited address; without SMTP the link is shown to the inviter
- Viewing and revoking pending invitations
- Service tokens (`envo_st_…`): one project, selected environments, optional write permission, expiry, revocation, last-used time; they appear as the token in the change history and audit logs
- Tests verifying that every API endpoint rejects unauthenticated and unauthorized requests

History and audit:

- Environment history: every change set, the person or token behind it, its source (web, CLI, token, rollback) and the changed keys; values are never shown
- Rollback: restores an environment to its state at an earlier revision, recorded as a new revision; requires write access
- Audit log screens at project, group (including subgroups and projects) and instance level (including sign-ins and admin actions); filtering and pagination
- GitHub Actions and GitLab CI examples (`examples/ci`) and a CLI release build script (`cli/scripts/build-release.sh`)

Folders and the `.env` editor:

- Each project has a single folder tree (e.g. `backend`, `services/api`); the structure is shared by all environments, and each folder has its own `.env` per environment
- On the environment page you pick a folder and edit its `.env` as text; saving replaces the folder's variables with the document (added, changed and deleted keys in one revision). Comments and line order are not kept
- Moving/renaming and deleting a folder creates a new revision in every affected environment; rolling back to an older revision also restores the folders as they were in that revision
- In the API the folder is chosen with `?path=`; without it the root folder is used
- The CLI finds the folder from the working directory (override with `--path`); `envo pull` at the project root (or `envo pull --all` anywhere) writes each folder's `.env` into its own directory
- Besides `.env`, any folder can hold config files that must not be committed (e.g. `application.properties`, `config.json`): placed on the project page, edited per environment as text on the environment page, stored encrypted exactly as written (up to 256 KB), and included in history, rollback and folder moves. API: `GET`/`PUT .../environments/{env}/files/{name}?path=`

Deployment:

- TLS is terminated at the reverse proxy in front (nginx + open-appsec); the required settings are below
- Backup, safe restore and restore-drill scripts; a command that verifies every stored value can be decrypted with the master key

## Local development

Requirements: Docker, Python 3.12+, Node 20+. If Go isn't installed, the CLI can be built with Docker.

### 1. Configuration

```powershell
Copy-Item backend/.env.example backend/.env
```

Change `ENVO_SECRET_KEY` in `backend/.env`:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`ENVO_MASTER_KEY` is the master key variables are encrypted with (32 bytes, base64). Store it separately from the database and back it up separately; without it the stored values cannot be decrypted.

```powershell
python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
```

To rotate the master key, set the new one as `ENVO_MASTER_KEY` and `ENVO_MASTER_KEY_ID`, move the old one into `ENVO_RETIRED_MASTER_KEYS` as `old_id:base64`, and rewrap the environment keys (values are not re-encrypted):

```powershell
cd backend; .venv\Scripts\python -m app.modules.variables.rotate
```

### 2. Single container (Docker Compose)

The API and dashboard run in one image (`earkin/envo`); build it from the repository root:

```powershell
docker build -t earkin/envo .
```

```powershell
docker compose up -d
```

Envo is served at `http://localhost:4400` (dashboard and `/api`); migrations run when the container starts. API docs: `http://localhost:4400/api/docs`.

### 3. Running the dashboard in dev mode

```powershell
npm --prefix frontend install
```

```powershell
npm --prefix frontend run dev
```

Open `http://localhost:5173`. Vite proxies `/api` requests to the backend (default `http://localhost:4400`). If you run the backend locally instead of in Docker, put `ENVO_API_PROXY=http://localhost:8000` in `frontend/.env.local`.

### Deploying to a server (behind a reverse proxy)

Envo does not do TLS; HTTPS is terminated at the reverse proxy in front (Nginx Proxy Manager / nginx + open-appsec). Add the container's port `4400` as a proxy host; since the dashboard and `/api` are served from the same address, one forwarding rule is enough:

- Target: `http://<server>:4400`
- The `X-Forwarded-For` and `X-Forwarded-Proto` headers must be forwarded (Nginx Proxy Manager does this by default).
- The request body limit must be at least 2 MB (`.env` import is at most 1 MiB).

`backend/.env` on the server (or environment variables):

- `ENVO_COOKIE_SECURE=true`: session cookies are only sent over HTTPS.
- `ENVO_FRONTEND_URL=https://envo.example.com`: invitation and `envo login` links use this address.
- `FORWARDED_ALLOW_IPS=<proxy IP or network>`: uvicorn only trusts `X-Forwarded-*` headers from this address. If unset, audit logs record the proxy's IP; don't set it to `*`. If the proxy runs in Docker, the address the container sees is usually the Docker network gateway (e.g. `172.17.0.1`).
- `ENVO_SECRET_KEY` and `ENVO_MASTER_KEY`: freshly generated values unique to the server (with the commands above).

Things to watch:

- Port `4400` must not be reachable directly from the internet; only the proxy should reach it (close it in the firewall). Otherwise requests bypass the WAF and TLS.
- **WAF and secret values:** variable write and import request bodies contain secrets (`POST /api/projects/*/environments/*/import`, `PUT`/`PATCH .../variables`), and `reveal` and `export` responses contain plaintext values. Make sure open-appsec does not log these request/response bodies. `.env` content (connection URLs, quotes, `$` signs) can trip injection rules; if it gets blocked, add exceptions for these paths.
- The CLI and CI use the same address: `envo login --api-url https://envo.example.com`.

### Backup and restore

A backup has two parts, and they must be stored separately:

- **Database dump:** encrypted values, password hashes, token hashes and history. Keep it encrypted and access-restricted.
- **Master key** (`ENVO_MASTER_KEY`, plus `ENVO_RETIRED_MASTER_KEYS` if you're mid-rotation): not in the database; store it elsewhere with different access rights (e.g. a password vault). Without the key the dump can't be decrypted, and without the dump the key reveals nothing.

On an instance running with Docker Compose (run the commands from the repository root):

```powershell
sh backend/scripts/backup.sh backups
```

This writes the backup to `backups/envo-<timestamp>.dump` with a `.sha256` next to it.

Restore drill: takes a fresh backup (or uses the given dump), restores it into a temporary database, verifies every stored value can be decrypted with the master key, and drops the temporary database:

```powershell
sh backend/scripts/restore-check.sh
```

Verification runs inside the `envo` service, where the master key is. Run the drill regularly (e.g. after every master key rotation and once a month).

A real restore:

1. Restore the backup into a new database: `sh backend/scripts/restore.sh <dump> envo_restored`. The script never overwrites an existing database and checks the checksum.
2. Verify: `docker compose exec envo python -m app.modules.variables.verify --database envo_restored`.
3. Stop the backend, point `ENVO_DATABASE_URL` at the new database (or rename it), run `alembic upgrade head` and start the backend.

If you use managed PostgreSQL, dump and restore with the provider's tools; the verify command is the same.

### Running the backend locally and tests

This needs PostgreSQL reachable on `localhost:5432`. The current `docker-compose.yml` doesn't expose the database port; in that case add `ports: ["5432:5432"]` to the `db` service. Tests use a separate `envo_test` database on the same server and create it if it doesn't exist.

```powershell
cd backend; python -m venv .venv; .venv\Scripts\pip install -e ".[dev]"
```

```powershell
cd backend; .venv\Scripts\alembic upgrade head; .venv\Scripts\uvicorn app.main:app --reload --port 8000
```

```powershell
cd backend; .venv\Scripts\pytest
```

### Email (invitations)

Set the `ENVO_SMTP_*` variables in `backend/.env`. For local testing you can use Mailpit (`ENVO_SMTP_HOST=localhost`, `ENVO_SMTP_PORT=1025`, `ENVO_SMTP_STARTTLS=false`; inbox at `http://localhost:8025`):

```powershell
docker run --rm -p 1025:1025 -p 8025:8025 axllent/mailpit
```

### Using it in CI

Create a service token on the project page and add it to CI as the `ENVO_TOKEN` secret. Since `envo.yaml` is in the repository, nothing else is needed:

```powershell
envo run --env staging -- npm test
```

### CLI

Requires Go 1.26. If Go isn't installed, you can test and build for Windows with Docker:

```powershell
docker run --rm -v "${PWD}/cli:/src" -w /src golang:1.26 go test ./...
```

```powershell
docker run --rm -v "${PWD}/cli:/src" -w /src -e GOOS=windows golang:1.26 go build -o envo.exe ./cmd/envo
```

Usage:

```powershell
envo login --api-url http://localhost:4400
```

```powershell
envo init --project acme/backend/web-api
```

```powershell
envo run --env development -- npm start
```

The server address is taken from, in order: `--api-url`, `ENVO_API_URL`, `envo.yaml`, and the last sign-in.

Folders: the directory containing `envo.yaml` is the project's root folder. `pull`, `push`, `set` and `run` use the deepest project folder that contains the working directory; for example, `envo run` run inside `backend/src` gets the `backend` folder's `.env`. `pull` writes the file into the folder's own directory, and `push` reads it from there. Pick a folder by hand with `--path backend`; use `--path /` for the root folder.

At the project root, `envo pull` writes every folder's `.env` into its own directory; `--all` does the same from anywhere in the project:

```powershell
envo pull
envo pull --all
```

To pull only the root folder's `.env` from the root, use `envo pull --path /`.

This also writes the project's config files (e.g. `backend/application.properties`). Folders with no directory in this checkout (left over from another revision of the code) and files that are empty in this environment are skipped. `envo push --replace` deletes keys that aren't in the file, the same way the web `.env` editor works.

A single config file is pulled or pushed by naming it (relative to the working directory); a push replaces the whole file in the environment, and writing a file the project doesn't have yet adds it:

```powershell
envo pull backend/application.properties
envo push backend/application.properties --env staging
```

Add config files to `.gitignore` like `.env`.
