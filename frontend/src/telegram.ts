// Тонкая обёртка над Telegram WebApp SDK. Безопасна вне Telegram (всё в try).

type AnyTg = any;

export const tg: AnyTg = (window as any).Telegram?.WebApp || null;

export function tgReady() {
  try {
    if (tg) {
      tg.ready();
      tg.expand();
      // Полноэкранный режим (Telegram 8.0+): открываемся сразу на весь экран,
      // чтобы случайный свайп вниз не сворачивал приложение. На старых клиентах
      // метода нет — тихо пропускаем, остаётся обычный развёрнутый режим.
      try {
        if (typeof tg.requestFullscreen === "function") tg.requestFullscreen();
      } catch {
        /* noop */
      }
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
  // source_link приходит из пользовательского поля → пускаем только http(s)/tg,
  // чтобы не открыть javascript:/data: и т.п. (находка L10).
  let safe = false;
  try {
    const scheme = new URL(url, window.location.href).protocol;
    safe = scheme === "http:" || scheme === "https:" || scheme === "tg:";
  } catch {
    safe = false;
  }
  if (!safe) return;
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


// Доступна ли нативная отправка подготовленного сообщения (Telegram 8.0+).
export function canShareMessage(): boolean {
  try {
    return typeof tg?.shareMessage === "function";
  } catch {
    return false;
  }
}

// Отправить подготовленное сообщение (prepared_message_id) в выбранный
// пользователем чат. Возвращает Promise<boolean> — было ли отправлено.
export function shareMessage(preparedId: string): Promise<boolean> {
  return new Promise((resolve) => {
    try {
      if (typeof tg?.shareMessage !== "function") {
        resolve(false);
        return;
      }
      tg.shareMessage(preparedId, (sent: boolean) => resolve(!!sent));
    } catch {
      resolve(false);
    }
  });
}
