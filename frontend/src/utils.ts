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
