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

- E-posta/parola ile kayıt ve giriş, HttpOnly cookie oturumu, CSRF koruması, döndürülen refresh token'lar ve tüm oturumları kapatma
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
- CI için `ENVO_TOKEN`

Faz 4 (ekip ve CI erişimi) tamamlandı:

- Hesabı olmayan e-postalara group veya proje daveti: 7 gün geçerli tek kullanımlık bağlantı, yalnızca davet edilen adresle kabul edilir; SMTP yoksa bağlantı davet edene gösterilir
- Bekleyen davetleri görme ve iptal etme
- Servis token'ları (`envo_st_…`): tek proje, seçili ortamlar, isteğe bağlı yazma izni, süre sınırı, iptal, son kullanım zamanı; değişiklik geçmişinde ve denetim kayıtlarında token olarak görünür
- Her API ucunun kimliksiz ve yetkisiz isteklere kapalı olduğunu doğrulayan testler

Faz 5 (P1) tamamlandı:

- Ortam geçmişi: her değişiklik kümesi, yapan kişi veya token, kaynak (web, CLI, token, geri alma) ve değişen anahtarlar; değerler gösterilmez
- Geri alma: ortamı önceki bir revizyondaki hâline döndürür, bunu yeni bir revizyon olarak kaydeder; yazma yetkisi gerekir
- Denetim kaydı ekranları: proje, group (alt group ve projeler dahil) ve kurulum düzeyinde (girişler ve yönetim işlemleri dahil); filtre ve sayfalama
- GitHub Actions ve GitLab CI örnekleri (`examples/ci`) ve CLI sürüm derleme betiği (`cli/scripts/build-release.sh`)

Dağıtım hazırlığı:

- TLS, önündeki ters vekilde (nginx + open-appsec) sonlandırılır; gereken ayarlar aşağıda
- Yedekleme, güvenli geri yükleme ve geri yükleme tatbikatı betikleri; saklanan her değerin ana anahtarla çözülebildiğini doğrulayan komut

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

### 2. Tek container (Docker Compose)

API ve dashboard tek imajda (`earkin/envo`) çalışır; imajı depo kökünden derleyin:

```powershell
docker build -t earkin/envo .
```

```powershell
docker compose up -d
```

Envo `http://localhost:4400` adresinde açılır (dashboard ve `/api`), migrasyonlar konteyner başlarken uygulanır. API dokümantasyonu: `http://localhost:4400/api/docs`.

### 3. Dashboard'u geliştirme modunda çalıştırma

```powershell
npm --prefix frontend install
```

```powershell
npm --prefix frontend run dev
```

`http://localhost:5173` adresini açın. Vite, `/api` isteklerini backend'e yönlendirir (varsayılan `http://localhost:4400`). Backend'i Docker yerine yerelde çalıştırıyorsanız `frontend/.env.local` dosyasına `ENVO_API_PROXY=http://localhost:8000` yazın.

### Sunucuya dağıtım (ters vekil arkasında)

Envo TLS yapmaz; HTTPS önündeki ters vekilde (Nginx Proxy Manager / nginx + open-appsec) sonlandırılır. Container'ın `4400` portunu vekilde bir proxy host olarak tanımlayın; dashboard ve `/api` aynı adresten sunulduğu için tek bir yönlendirme yeterlidir:

- Hedef: `http://<sunucu>:4400`
- `X-Forwarded-For` ve `X-Forwarded-Proto` başlıkları iletilmeli (Nginx Proxy Manager varsayılan olarak iletir).
- İstek gövdesi sınırı en az 2 MB olmalı (`.env` içe aktarma en fazla 1 MiB).

Sunucudaki `backend/.env` (veya ortam değişkenleri):

- `ENVO_COOKIE_SECURE=true`: oturum çerezleri yalnızca HTTPS üzerinden gider.
- `ENVO_FRONTEND_URL=https://envo.ornek.com`: davet ve `envo login` bağlantıları bu adresi kullanır.
- `FORWARDED_ALLOW_IPS=<vekilin IP'si veya ağı>`: uvicorn yalnızca bu adresten gelen `X-Forwarded-*` başlıklarına güvenir. Ayarlanmazsa denetim kayıtlarındaki IP vekilin IP'si olur; `*` yapmayın. Vekil Docker'da çalışıyorsa container'ın görünen adresi genellikle Docker ağının ağ geçididir (ör. `172.17.0.1`).
- `ENVO_SECRET_KEY` ve `ENVO_MASTER_KEY`: sunucuya özel, yeni üretilmiş değerler (yukarıdaki komutlarla).

Dikkat edilecekler:

- `4400` portuna internetten doğrudan erişilmemeli; yalnızca vekil ulaşabilsin (güvenlik duvarında kapatın). Aksi hâlde istekler WAF'ı ve TLS'i atlar.
- **WAF ve gizli değerler:** Değişken yazma ve içe aktarma isteklerinin gövdesinde secret'lar (`POST /api/projects/*/environments/*/import`, `PUT`/`PATCH .../variables`), `reveal` ve `export` yanıtlarında ise açık değerler bulunur. open-appsec'in bu istek/yanıt gövdelerini kaydetmediğinden emin olun. `.env` içerikleri (bağlantı adresleri, tırnaklar, `$` işaretleri) enjeksiyon kuralına takılabilir; engellenirse bu yollar için istisna tanımlayın.
- CLI ve CI aynı adresi kullanır: `envo login --api-url https://envo.ornek.com`.

### Yedekleme ve geri yükleme

Bir yedek iki parçadan oluşur ve ikisi birbirinden ayrı saklanmalıdır:

- **Veritabanı dökümü:** Şifreli değerler, parola özetleri, token özetleri ve geçmiş. Şifrelenmiş ve erişimi kısıtlı bir yerde tutun.
- **Ana anahtar** (`ENVO_MASTER_KEY` ve rotasyondaysanız `ENVO_RETIRED_MASTER_KEYS`): Veritabanında yoktur; farklı erişim yetkisiyle ayrı bir yerde (ör. parola kasası) saklayın. Anahtar olmadan döküm çözülemez, döküm olmadan anahtar bir şey açığa çıkarmaz.

Docker Compose ile çalışan bir kurulumda (komutları depo kökünde çalıştırın):

```powershell
sh backend/scripts/backup.sh backups
```

Yedeği `backups/envo-<zaman>.dump` ve yanında `.sha256` olarak yazar.

Geri yükleme tatbikatı: yeni yedek alır (veya verilen dökümü kullanır), geçici bir veritabanına geri yükler, saklanan her değerin ana anahtarla çözülebildiğini doğrular ve geçici veritabanını siler:

```powershell
sh backend/scripts/restore-check.sh
```

Doğrulama `envo` servisinin içinde çalışır; ana anahtar oradadır. Tatbikatı düzenli (ör. her ana anahtar değişiminden sonra ve ayda bir) çalıştırın.

Gerçek bir geri yükleme:

1. Yedeği yeni bir veritabanına açın: `sh backend/scripts/restore.sh <döküm> envo_restored`. Betik var olan bir veritabanının üzerine asla yazmaz ve checksum'ı kontrol eder.
2. Doğrulayın: `docker compose exec envo python -m app.modules.variables.verify --database envo_restored`.
3. Backend'i durdurun, `ENVO_DATABASE_URL`'yi yeni veritabanına yöneltin (veya adını değiştirin), `alembic upgrade head` çalıştırın ve backend'i başlatın.

Yönetilen PostgreSQL kullanıyorsanız döküm ve geri yüklemeyi sağlayıcının araçlarıyla yapın; doğrulama komutu aynıdır.

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

### E-posta (davetler)

`backend/.env` içinde `ENVO_SMTP_*` değişkenlerini tanımlayın. Yerelde denemek için Mailpit kullanılabilir (`ENVO_SMTP_HOST=localhost`, `ENVO_SMTP_PORT=1025`, `ENVO_SMTP_STARTTLS=false`; gelen kutusu `http://localhost:8025`):

```powershell
docker run --rm -p 1025:1025 -p 8025:8025 axllent/mailpit
```

### CI'da kullanım

Proje sayfasında bir servis token'ı oluşturun ve CI'da `ENVO_TOKEN` gizli değişkeni olarak tanımlayın. `envo.yaml` depoda olduğu için ek ayar gerekmez:

```powershell
envo run --env staging -- npm test
```

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
