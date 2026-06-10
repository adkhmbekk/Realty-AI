import { createContext, useContext } from "react";

// Действия переключения между платформой и личным агентством владельца.
// Реализованы в App (там доступен applyAuth/refresh), а используются глубоко
// в дереве (экран «Мои агентства», баннер). Отдельный модуль — чтобы не было
// циклического импорта между App и экранами.
export interface ActingActions {
  // Войти в личное агентство (id) как его главный админ.
  enterAgency: (id: number) => Promise<boolean>;
  // Выйти из агентства обратно на платформу (роль суперадмина).
  exitToPlatform: () => Promise<void>;
}

const Ctx = createContext<ActingActions | null>(null);
export const ActingProvider = Ctx.Provider;

export function useActing(): ActingActions {
  const v = useContext(Ctx);
  if (!v) throw new Error("useActing must be used within ActingProvider");
  return v;
}
