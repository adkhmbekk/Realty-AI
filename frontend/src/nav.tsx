import React, { createContext, useCallback, useContext, useState } from "react";
import type { Apartment, SearchParams } from "./types";

// Все экраны приложения. Стек хранит историю для кнопки «Назад».
export type Route =
  | { name: "home" }
  | { name: "profile" }
  | { name: "settings" }
  | { name: "agencies" }
  | { name: "agencyCreate" }
  | { name: "agencyManage"; id: number }
  | { name: "addObject" }
  | { name: "search" }
  | { name: "objectList"; params: SearchParams; titleKey: string }
  | { name: "objectDetail"; id: number }
  | { name: "objectEdit"; obj: Apartment }
  | { name: "archive" }
  | { name: "team" }
  | { name: "invites" }
  | { name: "analytics" }
  | { name: "agentDetail"; userId: number; agentName: string };

interface NavCtx {
  stack: Route[];
  current: Route;
  push: (r: Route) => void;
  pop: () => void;
  resetTo: (r: Route) => void;
}

const Ctx = createContext<NavCtx | null>(null);

export function useNav(): NavCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useNav must be used within NavProvider");
  return v;
}

export function NavProvider({ initial, children }: { initial: Route; children: React.ReactNode }) {
  const [stack, setStack] = useState<Route[]>([initial]);
  const push = useCallback((r: Route) => setStack((s) => [...s, r]), []);
  const pop = useCallback(() => setStack((s) => (s.length > 1 ? s.slice(0, -1) : s)), []);
  const resetTo = useCallback((r: Route) => setStack([r]), []);
  const current = stack[stack.length - 1];
  return <Ctx.Provider value={{ stack, current, push, pop, resetTo }}>{children}</Ctx.Provider>;
}
