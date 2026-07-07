import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { Apartment, MlsPoolItem, SearchParams } from "./types";

// Все экраны приложения. Стек хранит историю для кнопки «Назад».
export type Route =
  | { name: "home" }
  | { name: "profile" }
  | { name: "settings" }
  | { name: "agencies" }
  | { name: "myAgencies" }
  | { name: "mlsPool" }
  | { name: "mlsBrowse" }
  | { name: "toolSheets" }
  | { name: "toolFileImport" }
  | { name: "toolExcel" }
  | { name: "toolMassImport" }
  | { name: "toolWatch" }
  | { name: "agencyCreate" }
  | { name: "agencyManage"; id: number }
  | { name: "agencyObjects"; id: number }
  | { name: "agencyObjectDetail"; obj: Apartment; agencyId: number }
  | { name: "mlsObjectDetail"; item: MlsPoolItem }
  | { name: "addObject" }
  | { name: "search" }
  | { name: "objectList"; params: SearchParams; titleKey: string }
  | { name: "objectDetail"; id: number }
  | { name: "objectEdit"; obj: Apartment }
  | { name: "database" }
  | { name: "duplicates" }
  | { name: "archive" }
  | { name: "team" }
  | { name: "invites" }
  | { name: "analytics" }
  | { name: "agentDetail"; userId: number; agentName: string }
  | { name: "clients" }
  | { name: "clientDetail"; id: number }
  | { name: "clientMatches"; clientId: number; requestId: number; label?: string }
  | { name: "matches" }
  | { name: "saveRequest"; criteria: SearchParams };

// Живая страница: стабильный id (чтобы React НЕ размонтировал её при перерисовке
// и сохранял состояние/скролл) + сам маршрут.
export interface Pane {
  id: string;
  route: Route;
}

interface NavCtx {
  // Активная вкладка (корневой маршрут её стека) — для подсветки нижней панели.
  activeTab: string;
  // Стек на КАЖДУЮ вкладку: переключение вкладок сохраняет их состояние.
  tabs: Record<string, Pane[]>;
  // Все живые страницы всех вкладок — для keep-alive рендера (все смонтированы).
  panes: Pane[];
  // id видимой (верхней активной) страницы — только она показана, остальные скрыты.
  activePaneId: string;
  // Совместимость со старым API:
  current: Route; // верх активного стека
  stack: Route[]; // активный стек (используется stack[0].name, stack.length)
  push: (r: Route) => void;
  pop: () => void;
  resetTo: (r: Route) => void; // жёсткий сброс всей навигации (выход из acting и т.п.)
  switchTab: (r: Route) => void; // нижняя вкладка: сохранить всё; повторный тап → корень
}

const Ctx = createContext<NavCtx | null>(null);

export function useNav(): NavCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useNav must be used within NavProvider");
  return v;
}

// Активна ли текущая страница (видима). Экраны берут это для «умного обновления»
// при возврате (см. useRevisit в refresh.ts). По умолчанию true — вне keep-alive
// хоста экран считается активным.
export const PaneActiveContext = createContext<boolean>(true);
export function usePaneActive(): boolean {
  return useContext(PaneActiveContext);
}

let _seq = 0;
const nextId = () => `p${++_seq}`;

// Вкладка и стеки — в ОДНОМ состоянии, чтобы все переходы были атомарными и
// колбэки читали актуальные данные через функциональный апдейт (без ref-хаков,
// устойчиво к прерванному рендеру Suspense/concurrent).
interface NavState {
  activeTab: string;
  tabs: Record<string, Pane[]>;
}

export function NavProvider({ initial, children }: { initial: Route; children: React.ReactNode }) {
  const [state, setState] = useState<NavState>(() => ({
    activeTab: initial.name,
    tabs: { [initial.name]: [{ id: nextId(), route: initial }] },
  }));

  const push = useCallback((r: Route) => {
    const entry = { id: nextId(), route: r };
    setState((s) => {
      const cur = s.tabs[s.activeTab] ?? [];
      return { ...s, tabs: { ...s.tabs, [s.activeTab]: [...cur, entry] } };
    });
  }, []);

  const pop = useCallback(() => {
    setState((s) => {
      const cur = s.tabs[s.activeTab] ?? [];
      if (cur.length <= 1) return s;
      return { ...s, tabs: { ...s.tabs, [s.activeTab]: cur.slice(0, -1) } };
    });
  }, []);

  // Жёсткий сброс: одна вкладка, чистый стек (выход из acting-режима и т.п.).
  const resetTo = useCallback((r: Route) => {
    setState({ activeTab: r.name, tabs: { [r.name]: [{ id: nextId(), route: r }] } });
  }, []);

  // Нижняя вкладка. Другая вкладка → переключаемся, сохраняя обе. Та же вкладка →
  // возвращаемся к её корню (привычное поведение iOS/Telegram).
  const switchTab = useCallback((r: Route) => {
    const rootEntry = { id: nextId(), route: r };
    setState((s) => {
      if (s.activeTab === r.name) {
        const cur = s.tabs[r.name] ?? [];
        if (cur.length <= 1) return s;
        return { activeTab: r.name, tabs: { ...s.tabs, [r.name]: [cur[0]] } };
      }
      const tabs = s.tabs[r.name] ? s.tabs : { ...s.tabs, [r.name]: [rootEntry] };
      return { activeTab: r.name, tabs };
    });
  }, []);

  const { activeTab, tabs } = state;
  const activeStack = tabs[activeTab] ?? [];
  const top = activeStack[activeStack.length - 1];
  const current = top?.route ?? initial;
  const activePaneId = top?.id ?? "";
  const stack = useMemo(() => activeStack.map((p) => p.route), [activeStack]);
  // Все живые панели всех вкладок (порядок: по вкладкам, внутри — по глубине).
  const panes = useMemo(() => {
    const all: Pane[] = [];
    for (const name of Object.keys(tabs)) all.push(...tabs[name]);
    return all;
  }, [tabs]);

  const value: NavCtx = {
    activeTab,
    tabs,
    panes,
    activePaneId,
    current,
    stack,
    push,
    pop,
    resetTo,
    switchTab,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
