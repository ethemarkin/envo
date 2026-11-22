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
  last_owner: "Organizasyonda en az bir Owner kalmalıdır.",
  last_login_method: "Tek giriş yönteminizi kaldıramazsınız. Önce bir parola belirleyin.",
  organization_not_found: "Organizasyon bulunamadı.",
  project_not_found: "Proje bulunamadı.",
  environment_not_found: "Ortam bulunamadı.",
  // Google sign-in redirects (?error=...)
  google_failed: "Google ile giriş tamamlanamadı.",
  account_exists:
    "Bu e-posta ile zaten bir Envo hesabı var. Parolanızla giriş yapıp Google hesabınızı Ayarlar sayfasından bağlayın.",
  email_not_verified: "Google hesabınızın e-posta adresi doğrulanmamış.",
  identity_linked_elsewhere: "Bu Google hesabı başka bir Envo hesabına bağlı.",
  session_expired: "Oturumunuz sona erdi. Lütfen tekrar giriş yapın.",
};

export function errorMessage(error: unknown): string {
  const code = error instanceof ApiError ? error.code : typeof error === "string" ? error : "";
  return MESSAGES[code] ?? "Beklenmeyen bir hata oluştu.";
}

export const ROLE_LABELS = {
  owner: "Owner",
  admin: "Admin",
  developer: "Developer",
  viewer: "Viewer",
} as const;
