import type { Lang } from "./i18n";

export function fmtDate(iso: string | null | undefined, lang: Lang, tz?: string | null, notSet = "—"): string {
  if (!iso) return notSet;
  try {
    const d = new Date(iso);
    const dOpts: Intl.DateTimeFormatOptions = tz ? { timeZone: tz } : {};
    const tOpts: Intl.DateTimeFormatOptions = tz
      ? { hour: "2-digit", minute: "2-digit", timeZone: tz }
      : { hour: "2-digit", minute: "2-digit" };
    const loc = lang === "en" ? "en-GB" : lang === "uz" ? "uz-UZ" : "ru-RU";
    return d.toLocaleDateString(loc, dOpts) + " " + d.toLocaleTimeString(loc, tOpts);
  } catch {
    return iso;
  }
}

export function daysLeft(iso: string | null | undefined): number {
  if (!iso) return 0;
  const end = new Date(iso).getTime();
  return Math.max(0, Math.ceil((end - Date.now()) / 86400000));
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      window.prompt("Copy:", text);
    } catch {
      /* noop */
    }
    return false;
  }
}

export function initials(name?: string | null): string {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "";
  const a = parts[0][0] || "";
  const b = parts.length > 1 ? parts[parts.length - 1][0] || "" : "";
  return (a + b).toUpperCase();
}

export function fmtPrice(price?: number | null, currency?: string | null): string | null {
  if (price == null) return null;
  let str: string;
  if (Number.isInteger(price)) str = price.toLocaleString("ru-RU").replace(/,/g, " ");
  else str = String(price);
  return `${str} ${currency || ""}`.trim();
}


// Примечание: downscaleImage (возвращавший Blob для multipart) удалён как
// мёртвый код. Для загрузки используется downscaleToDataUrl (data-URL в JSON).


// Сжать изображение и вернуть data-URL (JPEG) для отправки в JSON.
// 2048px / q0.92 — высокое качество при разумном весе (фото чёткие, но запрос
// не настолько тяжёлый, чтобы тормозить загрузку через туннель).
export async function downscaleToDataUrl(file: File, maxDim = 2048, quality = 0.92): Promise<string> {
  try {
    const bitmap = await createImageBitmap(file);
    const { width, height } = bitmap;
    const scale = Math.min(1, maxDim / Math.max(width, height));
    const w = Math.max(1, Math.round(width * scale));
    const h = Math.max(1, Math.round(height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("no 2d context");
    ctx.drawImage(bitmap, 0, 0, w, h);
    bitmap.close?.();
    return canvas.toDataURL("image/jpeg", quality);
  } catch {
    // Запасной путь: прочитать исходный файл как data-URL.
    return await new Promise<string>((resolve, reject) => {
      const fr = new FileReader();
      fr.onload = () => resolve(String(fr.result));
      fr.onerror = () => reject(new Error("read failed"));
      fr.readAsDataURL(file);
    });
  }
}
