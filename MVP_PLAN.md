# Envo MVP geliştirme planı

Envo, ekiplerin uygulama yapılandırmasını ve secret’larını proje ve ortam bazında güvenli biçimde yönetmesini sağlayan bir geliştirici aracıdır. MVP sonunda bir geliştirici kaydolabilmeli, proje oluşturabilmeli, mevcut `.env` içeriğini güvenle aktarabilmeli ve aynı yapılandırmayı başka bir makinede veya CI/CD hattında yetkisi dahilinde kullanabilmelidir. Bu plan, `Envo_MVP_Ozellikleri.pdf` içindeki kapsamı kaynak PDF kaldırıldıktan sonra da kullanılabilecek şekilde kaydeder.

## Ürün kapsamı

| Öncelik | Modül | Teslimat |
| --- | --- | --- |
| P0 | Kimlik doğrulama | E-posta ve parola ile kayıt ve giriş, Google ile giriş, oturum yenileme ve iptal. |
| P0 | Group’lar ve ekip | GitLab benzeri iç içe group’lar, group ve proje üyelikleri, miras alınan roller, instance yöneticisi. Davet e-postaları ekip yönetimi fazındadır. |
| P0 | Projeler | Proje oluşturma, düzenleme ve silme. |
| P0 | Ortamlar | Development, staging, production ve özel ortamlar. |
| P0 | Değişkenler | Anahtar-değer yönetimi, toplu düzenleme ve `.env` içe/dışa aktarma. |
| P0 | Secret’lar | Şifreli saklama, listede maskeleme ve yetkili açık değer erişimi. |
| P0 | Yetkilendirme | Owner, Admin, Developer ve Viewer rolleri, tüm işlemlerde sunucu tarafı denetimi. |
| P0 | CLI | `login`, `init`, `pull`, `push`, `set` ve `run` komutları. |
| P0 | Servis token’ları | CI/CD için kapsamı ve süresi sınırlandırılabilir, iptal edilebilir token’lar. |
| P1 | Denetim kayıtları | Değişiklik ve erişim olaylarının kaydı. |
| P1 | Sürüm geçmişi | Ortam düzeyinde değişiklik geçmişi ve geri alma. |
| P1 | CI/CD örnekleri | GitHub Actions ve GitLab CI kullanım örnekleri. |

Kubernetes operatörü, dinamik secret’lar, otomatik secret rotasyonu, kurumsal SSO (SAML ve group bazlı OIDC) ve gelişmiş politika motoru V2 kapsamına ayrılır. Google ile giriş kurumsal SSO sayılmaz ve MVP’dedir.

## Mimari ve dizin yapısı

PDF’de önerilen yığınla başlanır. Backend, FastAPI ve PostgreSQL ile çalışır ve web ile CLI için ortak OpenAPI sözleşmesini sunar. Veritabanı PostgreSQL 17’dir; erişim SQLAlchemy 2 (async, `asyncpg`) ile, şema değişiklikleri Alembic migrasyonlarıyla yapılır. Şifreli değerler `bytea`, denetim olaylarının ek verisi `jsonb` olarak saklanır. MVP için ayrı bir önbellek veya kuyruk (Redis vb.) kullanılmaz; CLI giriş kodları, davetler ve oturumlar da PostgreSQL’de tutulur. Yerelde Docker Compose içindeki PostgreSQL, dağıtımda herhangi bir yönetilen PostgreSQL hizmeti kullanılabilir. Dashboard React, TypeScript ve Tailwind CSS kullanır. CLI Go ile geliştirilir. Docker Compose yerel geliştirme ve dağıtım yapılandırmasını taşır.

```text
envo/
├── backend/
│   ├── app/
│   │   ├── core/            # Ayarlar, veritabanı ve ortak güvenlik bileşenleri
│   │   │   └── crypto/      # Envelope encryption ve KeyProvider
│   │   └── modules/
│   │       ├── auth/
│   │       ├── groups/        # İç içe group’lar, üyelikler, ağaç
│   │       ├── admin/         # Instance ayarları ve yöneticiler
│   │       ├── projects/
│   │       ├── environments/
│   │       ├── variables/     # Değişkenler, secret’lar ve .env aktarımı
│   │       ├── authorization/
│   │       ├── service_tokens/
│   │       ├── audit_logs/
│   │       └── versions/
│   ├── migrations/
│   └── tests/
├── frontend/
│   └── src/
│       ├── app/              # Rotalar ve uygulama kabuğu
│       └── features/
│           ├── auth/
│           ├── navigation/    # Sol ağaç, group sayfası, üyeler
│           ├── projects/
│           ├── environments/
│           ├── team/
│           ├── service-tokens/
│           └── settings/
├── cli/
│   ├── cmd/envo/             # CLI giriş noktası
│   └── internal/
│       ├── commands/
│       ├── api/
│       └── config/
├── examples/ci/              # P1 GitHub Actions ve GitLab CI örnekleri
├── .gitignore
└── MVP_PLAN.md
```

Dashboard solda group ve projelerin ağacını gösterir. Ekranlar giriş ve kayıt, group sayfası, proje detayı, ortam editörü, ekip yönetimi, servis token’ları ve ayarlardır. `.gitignore` kökten yönetilir. Geçici görseller ve deneme betikleri `/.scratch/` veya `/tmp/` altında tutulur. Ürün görselleri ve paylaşılan betikler kendi modüllerinde Git’e eklenebilir. `.env.example` dosyalarında sadece örnek değerler kullanılır.

## Veri modeli ve güvenlik

- Envo bir kurulum (instance) olarak çalışır; organizasyon katmanı yoktur. Group → alt group → … → Proje → Ortam → Değişkenler. Projeler bir group içinde ya da en üst seviyede durabilir. Group’lar ve projeler aynı üst öğe altında tek bir yol alanını paylaşır (ör. `acme/backend/web-api`). Her anahtar ortam içinde benzersizdir; secret olmak ayrı bir tür değil, değişkenin görünürlüğüdür, bu yüzden aynı anahtar iki kez tanımlanamaz.
- Kimlik doğrulama harici bir servise bağlı olmadan backend’de yapılır. Google ile giriş, Authlib ile OpenID Connect (authorization code + PKCE) akışı olarak uygulanır. Kullanıcılar `users`, giriş yöntemleri `user_identities` (sağlayıcı, sağlayıcıdaki `sub`) tablosunda tutulur; bir kullanıcının parolası, Google hesabı veya ikisi birden olabilir. Google hesabı, var olan bir kullanıcıya yalnızca Google `email_verified` bildiriyorsa ve kullanıcı giriş yapmışken bağlanır; e-posta eşleşmesiyle sessiz birleştirme yapılmaz. Google girişi de aynı Envo oturum token’larını üretir. GitHub gibi başka sağlayıcılar aynı yapıyla eklenebilir. Group bazlı kurumsal SSO (SAML, özel OIDC) V2 kapsamındadır.
- Parolalar Argon2id ile özetlenerek saklanır. Erişim için kısa ömürlü JWT, oturum yenileme için döndürülebilir ve iptal edilebilir refresh token kullanılır. Kullanıcı oturumları ve servis token’ları ayrı yetki kurallarıyla değerlendirilir.
- Web oturumunda token’lar `HttpOnly`, `Secure` ve `SameSite` işaretli cookie’lerde taşınır, JavaScript tarafından okunamaz. Refresh cookie’si yalnızca yenileme ucunun yoluna gönderilir. Cookie ile kimlik doğrulanan durum değiştiren isteklerde CSRF koruması uygulanır. CLI ve servis token’ları `Authorization` başlığını kullanır.
- Her istekte kullanıcının ilgili group veya projedeki etkin rolü ve işlem yetkisi sunucuda doğrulanır; rolü olmayan kullanıcıya kaynak 404 ile döner. Yetki kuralları aşağıdaki rol matrisinde tanımlanır.
- Tüm değişken değerleri, görünür olanlar dahil, AES-256-GCM ve envelope encryption ile saklanır (ayrıntı aşağıda). Değişken değerleri, parolalar ve token’lar uygulama loglarına ve denetim olaylarına yazılmaz. Dağıtımda TLS ve güvenli yedekleme zorunludur. Geri yükleme testi veritabanı ve anahtar erişimini birlikte doğrular.
- Servis token’ları `envo_st_` önekiyle üretilir; açık değer oluşturulduğunda bir kez gösterilir. Sunucu yalnızca SHA-256 özetini, kapsamını (tek proje, seçili ortamlar, okuma veya okuma+yazma), son kullanma ve son kullanım zamanını ve iptal durumunu saklar. Token’lar yalnızca kendi projelerinin ortam ve değişken uçlarını kullanabilir; kapsam dışındaki ortamlar onlar için yoktur (404).
- Davetler: hesabı olmayan bir e-posta üye olarak eklendiğinde 7 gün geçerli, tek kullanımlık bir bağlantı gönderilir (yalnızca özeti saklanır). Davet yalnızca aynı e-postayla giriş yapan kullanıcı tarafından kabul edilir ve bu, adresi doğrulanmış sayar. Aynı adrese yeniden davet eskisini geçersiz kılar.
- Her değişkenin bir görünürlüğü vardır: **görünür** (değer listede açık gösterilir) veya **gizli** (secret; listede maskelenir, açık değer ayrı yetki ister). Model GitLab CI/CD değişkenlerine benzer. Görünürlük değişken başına ayarlanır ve sonradan değiştirilebilir.
- `.env` ayrıştırması yalnızca sunucuda yapılır. Web ve CLI ham `.env` metnini aynı uca gönderir, böylece yorumlar, tırnaklar, `export ` öneki ve çok satırlı değerler için tek bir kural seti geçerli olur. `${VAR}` genişletmesi MVP’de yapılmaz, değerler olduğu gibi saklanır.
- Toplu aktarım **birleştirme** semantiğiyle çalışır: dosyadaki yeni anahtarlar eklenir, var olanların değeri güncellenir, dosyada olmayan anahtarlar silinmez. Değişken silme yalnızca web arayüzünden (veya tekil API çağrısıyla) yapılır. Var olan anahtarlar görünürlüklerini korur. Yeni anahtarların görünürlüğü web’de içe aktarma önizlemesinde anahtar başına seçilir; CLI’da yeni anahtarlar varsayılan olarak gizli oluşturulur, `--visible KEY` ile görünür yapılabilir.
- Toplu aktarım girdi doğrulamasından sonra tek işlemde uygulanır. Yinelenen veya geçersiz anahtar varsa hiçbir değişiklik yapılmaz. Açık değer içeren export ve CLI pull, aynı yetki denetimine tabidir.

### Şifreleme

- **Ana anahtar (KEK):** 32 baytlık anahtar sunucuya veritabanı dışından verilir (`ENVO_MASTER_KEY` ortam değişkeni veya bağlanan bir dosya). Her KEK’in bir kimliği (`kek_id`) vardır; sunucu birden fazla KEK yükleyebilir, yeniler yalnızca güncel KEK ile yazılır. Anahtar erişimi `KeyProvider` arayüzünün arkasındadır, V2’de AWS KMS, GCP KMS veya Vault eklenebilir.
- **Veri anahtarı (DEK):** Her ortamın kendi rastgele DEK’i vardır. DEK, KEK ile sarılarak (`wrapped_dek`, `kek_id`) ortam satırında saklanır. Ortam silindiğinde DEK de silinir, eski yedeklerdeki şifreli veriler bu ortam için anlamsız hâle gelir.
- **Değer şifreleme:** Her değer için rastgele 96 bit nonce kullanılır. Saklama biçimi `biçim_sürümü | nonce | şifreli_metin+etiket` şeklindedir. AAD olarak `envo:v1:{environment_id}:{key}` verilir; böylece şifreli bir değer başka bir ortama veya anahtara kopyalanırsa çözülemez. Anahtar yeniden adlandırılırsa değer yeniden şifrelenir.
- **Rotasyon:** KEK rotasyonu yalnızca DEK’leri yeniden sarar, değerlere dokunmaz. DEK rotasyonu ortamdaki tüm değerleri tek işlemde yeniden şifreleyen bir yönetim komutudur. Otomatik secret rotasyonu V2 kapsamındadır.
- Şifreleme kodu `backend/app/core/crypto/` altında, iş mantığından bağımsız ve birim testli olarak tutulur.

### Rol matrisi

Üyelik GitLab’deki gibi group’lara ve projelere verilir ve aşağı doğru miras geçer: bir kullanıcının bir group veya projedeki etkin rolü, oradaki doğrudan rolü ile üst group’lardaki rollerinin en yükseğidir. Instance yöneticileri her yerde Owner’dır. Kurulumda ilk kaydolan kullanıcı yönetici olur; yöneticiler en üst seviyede group/proje oluşturmayı herkese açabilir veya kendilerine ayırabilir (varsayılan: açık). En üst seviyede group veya proje oluşturan kişi onun Owner’ı olur; alt öğeler yetkiyi üstten alır. Ortamların bir `protected` bayrağı vardır; production ortamı varsayılan olarak korumalı oluşturulur.

| İşlem | Owner | Admin | Developer | Viewer |
| --- | --- | --- | --- | --- |
| Group veya projeyi silme | ✓ | – | – | – |
| Group/proje adı, yolu, açıklaması; üye ekleme, rol değiştirme, üye çıkarma (Owner hariç) | ✓ | ✓ | – | – |
| Group içinde alt group ve proje oluşturma | ✓ | ✓ | – | – |
| Ortam oluşturma, düzenleme, silme, `protected` ayarı | ✓ | ✓ | – | – |
| Anahtarları ve görünür değerleri listeleme | ✓ | ✓ | ✓ | ✓ |
| Korumasız ortamda gizli değer okuma, `pull`, `run`, export | ✓ | ✓ | ✓ | – |
| Korumasız ortamda yazma, silme, geri alma | ✓ | ✓ | ✓ | – |
| Korumalı ortamda gizli değer okuma, `pull`, `run`, export | ✓ | ✓ | – | – |
| Korumalı ortamda yazma, silme, geri alma | ✓ | ✓ | – | – |
| Servis token’ı oluşturma ve iptal | ✓ | ✓ | – | – |
| Denetim kayıtlarını görüntüleme | ✓ | ✓ | – | – |

- Admin, Owner rolü veremez ve Owner’ı değiştiremez. En üst seviyedeki her group ve projede en az bir doğrudan Owner bulunur. Miras gelen üyelikler yalnızca geldikleri group’ta değiştirilir.
- Servis token’ları rol taşımaz, yalnızca kendi kapsamıyla değerlendirilir (tek proje, seçili ortamlar, okuma ve/veya yazma). Korumalı ortam ancak token kapsamına açıkça eklenmişse erişilebilir.
- Yetki kontrolü tek bir politika fonksiyonunda (`can(actor, action, resource)`) toplanır ve FastAPI bağımlılığı olarak her uca eklenir. Testler bu tablodan üretilen matrisle tüm uçları dener.

### Sürüm geçmişi ve denetim kayıtları

Ekranları P1 olsa da veri modeli faz 2’de kurulur ve kayıt yazımı o zamandan başlar.

- `variables` tablosu ortamın güncel durumunu tutar. Her ortamın artan bir `revision` sayacı vardır.
- Her yazma işlemi (tekil düzenleme, toplu aktarım, silme, görünürlük değişikliği, geri alma) tek bir işlemde ortamın `revision` değerini bir artırır, `environment_revisions` tablosuna bir değişiklik kümesi (yapan, kaynak: web/cli/token/rollback, zaman) ve `variable_revisions` tablosuna değişen her anahtar için bir satır (işlem türü, yeni şifreli değer, görünürlük) ekler. Geçmiş tabloları yalnızca eklenir, güncellenmez.
- Geri alma, N numaralı revizyondaki durumu hesaplar ve aradaki farkı **yeni bir revizyon** olarak uygular; geçmiş yeniden yazılmaz. Geri alma, hedef ortamdaki yazma yetkisini gerektirir.
- Web editörü kaydederken bildiği `revision` değerini gönderir (`If-Match`); arada başka biri değişiklik yaptıysa sunucu 409 döner. CLI `push` birleştirme yaptığı için bu denetim CLI’da isteğe bağlıdır.
- `audit_events` tablosu değişiklik ve erişim olaylarını tutar: giriş, üyelik ve rol değişiklikleri, token oluşturma ve iptali, gizli değer okuma, `pull`, `run` ve export. Olaylarda değer bulunmaz, yalnızca yapan, işlem, kaynak, IP, istemci ve zaman bulunur.
- MVP’de geçmiş ve denetim kayıtları için saklama süresi sınırı yoktur.

## CLI sözleşmesi

| Komut | Beklenen davranış |
| --- | --- |
| `envo login` | Tarayıcı akışıyla oturum açar: CLI bir onay kodu ve URL gösterir, tarayıcıyı açar, kullanıcı web’de girişli olarak isteği onaylar, CLI token’ı alır (device authorization benzeri akış). Tarayıcı açılamazsa URL ve kod elle kullanılır. Token işletim sisteminin anahtarlığında (Windows Credential Manager, macOS Keychain, Secret Service) saklanır. |
| `envo init` | Çalışma dizinini Envo projesine bağlar ve kökte `envo.yaml` oluşturur (projenin tam yolu ve kimliği, varsayılan ortam; bağ kimlikle kurulduğu için proje yeniden adlandırılsa da çalışır). Bu dosya secret içermez ve ekipçe paylaşılmak üzere Git’e eklenir. `.env` projenin `.gitignore` dosyasında yoksa eklenmesini önerir. Kişisel ayarlar (ör. farklı varsayılan ortam) Git’e eklenmeyen `.envo/` dizininde tutulur. |
| `envo pull --env development` | Yetkili ortam yapılandırmasını `.env` olarak dışa aktarır. Var olan dosyayı değiştirmek için açık onay veya seçenek ister. |
| `envo push --env staging` | Yerel `.env` metnini sunucuya gönderir; sunucu ayrıştırır, doğrular ve birleştirerek uygular. Dosyada olmayan anahtarlar silinmez. Yeni anahtarlar varsayılan olarak gizlidir, `--visible KEY` ile görünür yapılır. |
| `envo set DATABASE_URL --env production` | Anahtarın değerini gizli istem veya standart girdiden alır ve yazma yetkisini sunucuda denetler. |
| `envo run --env development -- npm start` | Değerleri alt sürecin ortamına aktarır, diskte `.env` oluşturmadan komutu çalıştırır ve çıkış kodunu iletir. |

## Geliştirme sırası

1. **Temel platform.** Modül iskeletinden çalıştırılabilir FastAPI, React ve Go giriş noktalarına geç. PostgreSQL migrasyonlarını ve Docker Compose ortamını kur. Kayıt, oturum, group, proje ve ortam yönetimini geliştir. Erişim izolasyonunu ve en erken ihtiyaç duyulan rol kontrollerini bu fazda uygula.
2. **Yapılandırma ve secret yönetimi.** Şifreleme ve anahtar erişimini kur. Revizyon ve denetim olaylarının yazımını bu fazda başlat. Ortam editörünü, değişken ve secret işlemlerini, toplu düzenlemeyi ve `.env` aktarımını yap. Açık değer erişimi, maskeleme, rol kontrolleri ve toplu işlem bütünlüğünü uçtan uca doğrula.
3. **CLI.** Altı komutu ortak API’ye bağla. `run` için alt süreç ortamı, çıkış kodu ve diskte dosya oluşmaması davranışlarını Windows ve Linux üzerinde doğrula.
4. **Ekip yönetimi ve CI erişimi.** Ekip daveti ve yönetim ekranını tamamla, rol matrisini tüm uçlarda doğrula. Servis token’ı oluşturma, süresini ve kapsamını sınırlama, iptal etme ve CI içinde kullanma akışlarını tamamla.
5. **P1 teslimatları.** Değişiklik ve erişim olaylarını görüntüle, ortam sürüm geçmişi ve yetkili geri alma işlemini ekle. GitHub Actions ve GitLab CI örneklerini servis token’larıyla doğrula.

## MVP kabul senaryoları

- Kullanıcı kaydolur, bir group ve proje oluşturur, bir ortam seçer ve `.env` içeriğini yükler. Başka bir bilgisayarda yetkili CLI oturumu aynı anahtar-değer kümesini alır.
- Bir ekip daveti kabul edilir. Viewer yalnızca izin verilen maskeli görünümü alır. Yetkisiz kullanıcılar açık değer okuyamaz, ortamı değiştiremez ve üyesi olmadığı group ve projelerin kaynaklarına erişemez.
- Yetkili bir CI işi servis token’ıyla yapılandırmayı alır. Süresi dolmuş, iptal edilmiş veya kapsamı dışında kullanılan token reddedilir.
- `envo run` yapılandırmayı alt sürece geçirir, `.env` yazmaz ve alt sürecin çıkış kodunu döndürür. İşlem sırasında secret veya token değerleri loglarda görünmez.
- Geçersiz toplu aktarım ortamı kısmen değiştirmez. Yetkili export, desteklenen değerleri yeniden import edilebilir biçimde verir.
- Dağıtımda TLS kullanılır. Şifreli verilerin güvenli yedekten geri yüklenebildiği ve anahtarların ayrı erişimle yönetildiği doğrulanır.
