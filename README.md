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
- GitLab benzeri iç içe group'lar ve kökte projeler; group ve proje üyelikleri, aşağı doğru miras alınan roller, instance yöneticisi (ilk kullanıcı)
- Dashboard: solda group/proje ağacı, group ve proje sayfaları, üye yönetimi, ayarlar ve yönetici paneli

Faz 2 (yapılandırma ve secret yönetimi) tamamlandı:

- Tüm değerler AES-256-GCM ve envelope encryption ile saklanır: ortam başına veri anahtarı, veritabanı dışından verilen ana anahtar, ortam ve anahtar adına bağlı AAD
- Görünür ve gizli değişkenler, rol ve korumalı ortam kurallarına göre gizli değer okuma, yazma ve dışa aktarma
- Sunucuda `.env` ayrıştırma, birleştirme semantiğiyle içe aktarma (önizleme dahil) ve yeniden içe aktarılabilir dışa aktarma
- Her yazmada ortam revizyonu, değişiklik geçmişi ve `If-Match` ile eşzamanlı düzenleme koruması; denetim kayıtları (değer içermez)
- Ortam editörü: düzenleme, gösterme, toplu kaydetme, `.env` içe/dışa aktarma

Faz 3 (CLI) tamamlandı:

- `envo login` tarayıcıdan onaylanan giriş (kod terminalde gösterilir, web'de elle girilir); token'lar işletim sisteminin anahtarlığında, yoksa `0600` izinli bir dosyada
- `envo init`, `pull`, `push`, `set`, `run`, ayrıca `logout` ve `whoami`
- `envo run` değerleri diske yazmadan alt sürece verir, sinyalleri iletir ve çıkış kodunu döndürür (Windows ve Linux'ta denendi)
- CI için `ENVO_TOKEN`; servis token'ları faz 4'te gelecek

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

`ENVO_MASTER_KEY` değişkenlerin şifrelendiği ana anahtardır (32 bayt, base64). Veritabanından ayrı saklayın ve ayrıca yedekleyin; bu anahtar olmadan kayıtlı değerler çözülemez.

```powershell
python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
```

Ana anahtarı değiştirmek için yenisini `ENVO_MASTER_KEY` ve `ENVO_MASTER_KEY_ID` olarak tanımlayın, eskisini `ENVO_RETIRED_MASTER_KEYS` içine `eski_id:base64` olarak taşıyın ve ortam anahtarlarını yeniden sarın (değerler yeniden şifrelenmez):

```powershell
cd backend; .venv\Scripts\python -m app.modules.variables.rotate
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

Go 1.26 gerekir. Go kurulu değilse Docker ile test edip Windows için derleyebilirsiniz:

```powershell
docker run --rm -v "${PWD}/cli:/src" -w /src golang:1.26 go test ./...
```

```powershell
docker run --rm -v "${PWD}/cli:/src" -w /src -e GOOS=windows golang:1.26 go build -o envo.exe ./cmd/envo
```

Kullanım:

```powershell
envo login --api-url http://localhost:4400
```

```powershell
envo init --project acme/backend/web-api
```

```powershell
envo run --env development -- npm start
```

Sunucu adresi sırasıyla `--api-url`, `ENVO_API_URL`, `envo.yaml` ve son girişten alınır.
