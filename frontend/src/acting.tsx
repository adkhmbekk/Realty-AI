import { createContext, useContext } from "react";

// Действия переключения между платформой и личным агентством владельца.
// Реализованы в App (там доступен applyAuth/refresh), а используются глубоко
// в дереве (экран «Мои агентства», баннер). Отдельный модуль — чтобы не было
// циклического импорта между App и экранами.
export interface ActingActions {
  // Войти в другое своё агентство (id) — переключение (acting-контекст).
  enterAgency: (id: number) => Promise<boolean>;
  // Выйти из агентства обратно домой/на платформу.
  exitToPlatform: () => Promise<void>;
  // Открыть ЕЩЁ ОДНО своё агентство (участник станет его владельцем) и войти в него.
  openAgency: (name: string, phone: string) => Promise<boolean>;
}

const Ctx = createContext<ActingActions | null>(null);
export const ActingProvider = Ctx.Provider;

export function useActing(): ActingActions {
  const v = useContext(Ctx);
  if (!v) throw new Error("useActing must be used within ActingProvider");
  return v;
}
