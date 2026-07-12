import React from "react";

// Верхнеуровневый «предохранитель»: ловит ЛЮБУЮ ошибку рендера (в т.ч. падение
// загрузки lazy-чанка после нового деплоя или моргания туннеля) и показывает
// карточку «обновить» вместо белого экрана (CR-3). Без этого один сбой отрисовки
// размонтировал всё дерево React — приложение «умирало» без выхода.

const MSG: Record<string, { title: string; body: string; btn: string }> = {
  ru: {
    title: "Что-то пошло не так",
    body: "Приложение столкнулось с ошибкой. Обновите страницу — обычно это помогает.",
    btn: "Обновить",
  },
  uz: {
    title: "Nimadir xato ketdi",
    body: "Ilovada xatolik yuz berdi. Sahifani yangilang — odatda shu yordam beradi.",
    btn: "Yangilash",
  },
  en: {
    title: "Something went wrong",
    body: "The app hit an error. Reloading usually fixes it.",
    btn: "Reload",
  },
};

function currentLang(): "ru" | "uz" | "en" {
  const s = localStorage.getItem("pa_lang");
  return s === "uz" || s === "en" ? s : "ru";
}

// Ошибка загрузки динамического модуля (сменились хеши чанков после деплоя, либо
// туннель моргнул на середине навигации). Такое лечится перезагрузкой свежих файлов.
function isChunkLoadError(err: unknown): boolean {
  const m = String((err as { message?: string })?.message || err || "");
  return /dynamically imported module|Loading chunk|Importing a module script failed|Failed to fetch/i.test(m);
}

const RELOADED_KEY = "pa_chunk_reloaded";

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: unknown): void {
    // Сбой загрузки чанка — один раз перезагружаемся сами (флаг в sessionStorage
    // защищает от петли, если перезагрузка не помогла).
    if (isChunkLoadError(error) && !sessionStorage.getItem(RELOADED_KEY)) {
      sessionStorage.setItem(RELOADED_KEY, "1");
      window.location.reload();
    }
  }

  private reload = (): void => {
    sessionStorage.removeItem(RELOADED_KEY);
    window.location.reload();
  };

  render(): React.ReactNode {
    if (!this.state.hasError) return this.props.children;
    const L = MSG[currentLang()];
    return (
      <div
        style={{
          maxWidth: 480,
          margin: "0 auto",
          padding: "80px 20px",
          textAlign: "center",
          fontFamily: "system-ui, -apple-system, sans-serif",
        }}
      >
        <div style={{ fontSize: 40, marginBottom: 12 }}>⚠️</div>
        <h1 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>{L.title}</h1>
        <p style={{ opacity: 0.7, marginBottom: 20, lineHeight: 1.5 }}>{L.body}</p>
        <button
          onClick={this.reload}
          style={{
            padding: "10px 22px",
            borderRadius: 10,
            border: "none",
            background: "#2563eb",
            color: "#fff",
            fontWeight: 600,
            fontSize: 15,
            cursor: "pointer",
          }}
        >
          {L.btn}
        </button>
      </div>
    );
  }
}
