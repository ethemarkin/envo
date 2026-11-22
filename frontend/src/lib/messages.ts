import { ApiError } from "./api";

// Backend error codes → user-facing text.
const MESSAGES: Record<string, string> = {
  invalid_credentials: "E-posta veya parola hatalı.",
  email_taken: "Bu e-posta adresiyle zaten bir hesap var.",
  validation_error: "Girilen bilgileri kontrol edin.",
  slug_taken: "Bu kısa ad zaten kullanılıyor.",
  forbidden: "Bu işlem için yetkiniz yok.",
  csrf_failed: "Oturum doğrulanamadı. Sayfayı yenileyip tekrar deneyin.",
  not_authenticated: "Oturumunuz sona erdi. Lütfen tekrar giriş yapın.",
  last_owner: "En üst seviyedeki her group ve projede en az bir doğrudan Owner kalmalıdır.",
  group_not_found: "Group bulunamadı veya erişiminiz yok.",
  root_creation_disabled:
    "Bu kurulumda en üst seviyede group veya proje oluşturma yöneticilere ayrılmış. Bir group içinde oluşturun ya da bir yöneticiye başvurun.",
  user_not_found: "Bu e-posta ile kayıtlı bir kullanıcı yok.",
  already_member: "Bu kullanıcı zaten doğrudan üye.",
  member_not_found: "Üyelik bulunamadı.",
  admin_required: "Bu işlem yalnızca yöneticilere açık.",
  last_admin: "Kurulumda en az bir yönetici kalmalıdır.",
  invitation_not_found: "Bu davet geçersiz, süresi dolmuş, iptal edilmiş veya zaten kullanılmış.",
  invitation_email_mismatch:
    "Bu davet başka bir e-posta adresine gönderildi. Davetin geldiği adresle giriş yapın.",
  invitation_required:
    "Bu kurulumda hesaplar yalnızca davetle açılır. Size gelen davet bağlantısını kullanın.",
  cannot_delete_self: "Kendi hesabınızı silemezsiniz.",
  service_token_not_found: "Servis token'ı bulunamadı.",
  invalid_environment: "Seçilen ortamlar bu projeye ait değil.",
  service_token_not_allowed: "Servis token'ları bu işlem için kullanılamaz.",
  revision_not_found: "Bu revizyon bulunamadı.",
  invalid_cursor: "Sayfa bağlantısı geçersiz; listeyi yenileyin.",
  project_not_found: "Proje bulunamadı veya erişiminiz yok.",
  environment_not_found: "Ortam bulunamadı.",
  revision_conflict:
    "Bu ortam siz düzenlerken başka biri tarafından değiştirildi. Güncel hâli yükleyip değişikliklerinizi tekrar uygulayın.",
  invalid_dotenv: ".env içeriğinde hatalar var.",
  invalid_key: "Geçersiz anahtar. Harf, rakam ve alt çizgi kullanın; rakamla başlamasın.",
  duplicate_key: "Aynı anahtar birden fazla kez tanımlanmış.",
  value_required: "Yeni değişkenler için değer girilmelidir.",
  variable_not_found: "Değişken bulunamadı.",
  value_too_long: "Değer çok uzun (en fazla 64 KB).",
  encryption_not_configured: "Sunucuda şifreleme anahtarı yapılandırılmamış.",
  cli_request_not_found:
    "Bu kodla bekleyen bir CLI girişi bulunamadı. Kodun süresi dolmuş olabilir; terminalde envo login komutunu yeniden çalıştırın.",
  session_expired: "Oturumunuz sona erdi. Lütfen tekrar giriş yapın.",
};

export function errorMessage(error: unknown): string {
  const code = error instanceof ApiError ? error.code : typeof error === "string" ? error : "";
  const message = MESSAGES[code] ?? "Beklenmeyen bir hata oluştu.";
  const keys = error instanceof ApiError ? error.data.keys : undefined;
  return Array.isArray(keys) && keys.length > 0 ? `${message} (${keys.join(", ")})` : message;
}

export const ROLE_LABELS = {
  owner: "Owner",
  admin: "Admin",
  developer: "Developer",
  viewer: "Viewer",
} as const;
