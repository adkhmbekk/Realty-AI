// Тонкая обёртка над Telegram WebApp SDK. Безопасна вне Telegram (всё в try).

type AnyTg = any;

export const tg: AnyTg = (window as any).Telegram?.WebApp || null;

export function tgReady() {
  try {
    if (tg) {
      tg.ready();
      tg.expand();
    }
  } catch {
    /* noop */
  }
}

export function getInitData(): string {
  try {
    return tg?.initData || "";
  } catch {
    return "";
  }
}

export function getStartParam(): string {
  try {
    return tg?.initDataUnsafe?.start_param || "";
  } catch {
    return "";
  }
}

export function colorScheme(): "light" | "dark" | null {
  try {
    return tg?.colorScheme === "dark" ? "dark" : tg?.colorScheme === "light" ? "light" : null;
  } catch {
    return null;
  }
}

export function setChromeColors(bg: string) {
  try {
    tg?.setBackgroundColor?.(bg);
  } catch {
    /* noop */
  }
  try {
    tg?.setHeaderColor?.(bg);
  } catch {
    /* noop */
  }
}

export function haptic(kind: "light" | "medium" | "heavy" = "light") {
  try {
    tg?.HapticFeedback?.impactOccurred?.(kind);
  } catch {
    /* noop */
  }
}

export function openTelegramLink(url: string) {
  try {
    if (tg?.openTelegramLink) tg.openTelegramLink(url);
    else window.open(url, "_blank");
  } catch {
    window.open(url, "_blank");
  }
}

export function openLink(url: string) {
  try {
    if (tg?.openLink) tg.openLink(url);
    else window.open(url, "_blank");
  } catch {
    window.open(url, "_blank");
  }
}

export function shareToTelegram(text: string) {
  const link = "https://t.me/share/url?url=&text=" + encodeURIComponent(text);
  openTelegramLink(link);
}
