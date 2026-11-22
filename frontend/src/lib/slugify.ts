const TR: Record<string, string> = { ç: "c", ğ: "g", ı: "i", ö: "o", ş: "s", ü: "u" };

/** Same rules as the backend's slugify (app/core/slugs.py), for previews. */
export function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[çğıöşü]/g, (c) => TR[c] ?? c)
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 50)
    .replace(/-+$/g, "");
}
