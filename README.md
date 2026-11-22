# Envo

Ekiplerin uygulama yapılandırmasını ve secret'larını proje ve ortam bazında yönetmesi için geliştirici aracı. Kapsam, mimari ve kararlar için [MVP_PLAN.md](MVP_PLAN.md).

| Dizin | İçerik |
| --- | --- |
| `backend/` | FastAPI + PostgreSQL API (SQLAlchemy 2, Alembic) |
| `frontend/` | React + TypeScript + Tailwind dashboard (Vite) |
| `cli/` | Go CLI (`envo`) |
| `examples/ci/` | CI/CD örnekleri (P1) |

## Durum

Faz 1 (temel platform) tamamlandı:

- E-posta/parola ile kayıt ve giriş, Google ile giriş (OIDC), HttpOnly cookie oturumu, CSRF koruması, döndürülen refresh token'lar ve tüm oturumları kapatma
- Organizasyon, üyelik, proje ve ortam yönetimi; organizasyon izolasyonu ve rol kontrolleri
- Dashboard: giriş/kayıt, organizasyonlar, proje detayı (ortamlar), ayarlar
- CLI giriş noktası; komutlar faz 3'te API'ye bağlanacak

## Yerel geliştirme

Gereksinimler: Docker, Python 3.12+, Node 20+. Go kurulu değilse CLI Docker ile derlenebilir.

### 1. Yapılandırma

```powershell
Copy-Item backend/.env.example backend/.env
```

`backend/.env` içindeki `ENVO_SECRET_KEY` değerini değiştirin:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. Veritabanı ve API (Docker Compose)

```powershell
docker compose up -d --build
```

API `http://localhost:4400` adresinde açılır, migrasyonlar konteyner başlarken uygulanır. Dokümantasyon: `http://localhost:4400/api/docs`.

### 3. Dashboard

```powershell
npm --prefix frontend install
```

```powershell
npm --prefix frontend run dev
```

`http://localhost:5173` adresini açın. Vite, `/api` isteklerini backend'e yönlendirir (varsayılan `http://localhost:4400`). Backend'i Docker yerine yerelde çalıştırıyorsanız `frontend/.env.local` dosyasına `ENVO_API_PROXY=http://localhost:8000` yazın.

### Backend'i yerelde çalıştırma ve testler

Bunun için PostgreSQL'e `localhost:5432` üzerinden erişilebilmesi gerekir. Mevcut `docker-compose.yml` veritabanı portunu dışarı açmıyor; bu durumda `db` servisine `ports: ["5432:5432"]` ekleyin. Testler, veritabanı ilk kez oluşturulurken açılan ayrı `envo_test` veritabanını kullanır.

```powershell
cd backend; python -m venv .venv; .venv\Scripts\pip install -e ".[dev]"
```

```powershell
cd backend; .venv\Scripts\alembic upgrade head; .venv\Scripts\uvicorn app.main:app --reload --port 8000
```

```powershell
cd backend; .venv\Scripts\pytest
```

### Google ile giriş

Google Cloud Console'da bir OAuth istemcisi (Web application) oluşturun ve yetkili yönlendirme adresi olarak `http://localhost:5173/api/auth/google/callback` ekleyin. İstemci kimliğini ve parolasını `backend/.env` içinde `ENVO_GOOGLE_CLIENT_ID` ve `ENVO_GOOGLE_CLIENT_SECRET` olarak tanımlayın. Bu değerler boşsa Google düğmesi gösterilmez.

### CLI

```powershell
docker run --rm -v "${PWD}/cli:/src" -w /src golang:1.24 go test ./...
```

Go kuruluysa: `cd cli; go run ./cmd/envo`.
