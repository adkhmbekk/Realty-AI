// Тонкая обёртка над Telegram WebApp SDK. Безопасна вне Telegram (всё в try).

type AnyTg = any;

export const tg: AnyTg = (window as any).Telegram?.WebApp || null;

export function tgReady() {
  try {
    if (tg) {
      tg.ready();
      tg.expand();
      // Полноэкранный режим (Telegram 8.0+): открываемся сразу на весь экран.
      try {
        if (typeof tg.requestFullscreen === "function") tg.requestFullscreen();
      } catch {
        /* noop */
      }
      // Запрет вертикальных свайпов (Telegram 7.7+): чтобы случайный свайп вниз
      // не сворачивал/не закрывал приложение в полноэкранном режиме.
      try {
        if (typeof tg.disableVerticalSwipes === "function") tg.disableVerticalSwipes();
      } catch {
        /* noop */
      }
      // Безопасный отступ сверху: в полном экране контент не должен заезжать
      // под шапку Telegram и вырез/часы телефона. Кладём отступ в CSS-переменную
      // --tg-top-inset и обновляем при изменениях (старые клиенты → 0, без вреда).
      applyTopInset();
      try {
        tg.onEvent?.("safeAreaChanged", applyTopInset);
        tg.onEvent?.("contentSafeAreaChanged", applyTopInset);
        tg.onEvent?.("fullscreenChanged", applyTopInset);
        tg.onEvent?.("viewportChanged", applyTopInset);
      } catch {
        /* noop */
      }
    }
  } catch {
    /* noop */
  }
}

// Сумма «системного» отступа (вырез/часы) и отступа под шапкой Telegram.
export function applyTopInset() {
  try {
    const sa = (tg && tg.safeAreaInset && tg.safeAreaInset.top) || 0;
    const csa = (tg && tg.contentSafeAreaInset && tg.contentSafeAreaInset.top) || 0;
    const top = Math.max(0, Number(sa) + Number(csa));
    document.documentElement.style.setProperty("--tg-top-inset", top + "px");
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

export function hapticNotify(kind: "success" | "error" | "warning" = "success") {
  try {
    tg?.HapticFeedback?.notificationOccurred?.(kind);
  } catch {
    /* noop */
  }
}

// Подтверждение опасного действия нативным диалогом Telegram (премиальнее, чем
// браузерный confirm). На старых клиентах — откат на window.confirm.
export function confirmDialog(message: string): Promise<boolean> {
  return new Promise((resolve) => {
    try {
      if (typeof tg?.showConfirm === "function") {
        tg.showConfirm(message, (ok: boolean) => resolve(!!ok));
        return;
      }
    } catch {
      /* noop */
    }
    resolve(window.confirm(message));
  });
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

// Открыть ссылку на ИСТОЧНИК объекта. Источник почти всегда — пост в
// Telegram-канале (t.me/…). Такие ссылки НЕЛЬЗЯ открывать через openLink: он
// уводит во внешний браузер, тот редиректит в Telegram, и Mini App при этом
// выгружается — теряется весь поиск/состояние (жалоба пользователя). Правильно:
// t.me/tg-ссылки открывать через openTelegramLink (канал показывается ПОВЕРХ
// приложения, Mini App остаётся живым), а обычные веб-ссылки — через openLink.
export function openSourceLink(url: string) {
  let u: URL | null = null;
  try {
    u = new URL(url, window.location.href);
  } catch {
    return;
  }
  // Безопасность: пускаем только http(s)/tg (source_link — пользовательское поле).
  if (u.protocol !== "http:" && u.protocol !== "https:" && u.protocol !== "tg:") return;
  const host = u.hostname.toLowerCase();
  const isTelegram =
    u.protocol === "tg:" ||
    host === "t.me" ||
    host === "telegram.me" ||
    host === "telegram.dog" ||
    host.endsWith(".t.me");
  if (isTelegram) openTelegramLink(url);
  else openLink(url);
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
