import React, { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Briefcase, Building2, Database, Home, Layers, Plus, Search, Settings as SettingsIcon, User } from "lucide-react";
import { useApp } from "./store";
import { NavProvider, Route, useNav } from "./nav";
import { ActingProvider, useActing } from "./acting";
import { api, errText, setReauthHandler } from "./api";
import { tg, tgReady, getInitData, getStartParam, haptic } from "./telegram";
import type { AuthResponse, AgencySettings } from "./types";
import { Button, Card, Field, Input, Spinner } from "./components/ui";
import { HomeScreen } from "./screens/Home";
import { ProfileScreen, SuspendedScreen } from "./screens/Profile";
// Экраны грузим «лениво» (code-splitting): начальный бандл меньше → быстрее
// первый показ при открытии. Часто открываемые Home и Profile оставляем в
// основном бандле (без мелькания загрузчика). Остальное подгружается при первом
// переходе и кэшируется. Все ленивые экраны рендерятся внутри <Suspense> в Shell.
const SettingsScreen = lazy(() => import("./screens/Settings").then((m) => ({ default: m.SettingsScreen })));
const ToolSheetsScreen = lazy(() => import("./screens/Settings").then((m) => ({ default: m.ToolSheetsScreen })));
const ToolFileImportScreen = lazy(() => import("./screens/Settings").then((m) => ({ default: m.ToolFileImportScreen })));
const ToolExcelScreen = lazy(() => import("./screens/Settings").then((m) => ({ default: m.ToolExcelScreen })));
const ToolMassImportScreen = lazy(() => import("./screens/Settings").then((m) => ({ default: m.ToolMassImportScreen })));
const ToolWatchScreen = lazy(() => import("./screens/Settings").then((m) => ({ default: m.ToolWatchScreen })));
const TeamScreen = lazy(() => import("./screens/Team").then((m) => ({ default: m.TeamScreen })));
const InvitesScreen = lazy(() => import("./screens/Invites").then((m) => ({ default: m.InvitesScreen })));
const AnalyticsScreen = lazy(() => import("./screens/Analytics").then((m) => ({ default: m.AnalyticsScreen })));
const AgentDetailScreen = lazy(() => import("./screens/AgentDetail").then((m) => ({ default: m.AgentDetailScreen })));
const AgenciesScreen = lazy(() => import("./screens/Superadmin").then((m) => ({ default: m.AgenciesScreen })));
const AgencyCreateScreen = lazy(() => import("./screens/Superadmin").then((m) => ({ default: m.AgencyCreateScreen })));
const AgencyManageScreen = lazy(() => import("./screens/Superadmin").then((m) => ({ default: m.AgencyManageScreen })));
const AgencyObjectsScreen = lazy(() => import("./screens/Superadmin").then((m) => ({ default: m.AgencyObjectsScreen })));
const AgencyObjectDetailScreen = lazy(() => import("./screens/Apartments").then((m) => ({ default: m.AgencyObjectDetailScreen })));
const MlsPoolScreen = lazy(() => import("./screens/Superadmin").then((m) => ({ default: m.MlsPoolScreen })));
const MyAgenciesScreen = lazy(() => import("./screens/Superadmin").then((m) => ({ default: m.MyAgenciesScreen })));
const AddObjectScreen = lazy(() => import("./screens/Apartments").then((m) => ({ default: m.AddObjectScreen })));
const ArchiveScreen = lazy(() => import("./screens/Apartments").then((m) => ({ default: m.ArchiveScreen })));
const DatabaseScreen = lazy(() => import("./screens/Apartments").then((m) => ({ default: m.DatabaseScreen })));
const DuplicatesScreen = lazy(() => import("./screens/Apartments").then((m) => ({ default: m.DuplicatesScreen })));
const ObjectDetailScreen = lazy(() => import("./screens/Apartments").then((m) => ({ default: m.ObjectDetailScreen })));
const ObjectEditScreen = lazy(() => import("./screens/Apartments").then((m) => ({ default: m.ObjectEditScreen })));
const ObjectList = lazy(() => import("./screens/Apartments").then((m) => ({ default: m.ObjectList })));
const SearchScreen = lazy(() => import("./screens/Apartments").then((m) => ({ default: m.SearchScreen })));
const MlsBrowseScreen = lazy(() => import("./screens/Apartments").then((m) => ({ default: m.MlsBrowseScreen })));
const ClientDetailScreen = lazy(() => import("./screens/Clients").then((m) => ({ default: m.ClientDetailScreen })));
const ClientsScreen = lazy(() => import("./screens/Clients").then((m) => ({ default: m.ClientsScreen })));
const ClientMatchesScreen = lazy(() => import("./screens/Clients").then((m) => ({ default: m.ClientMatchesScreen })));
const MatchesScreen = lazy(() => import("./screens/Clients").then((m) => ({ default: m.MatchesScreen })));
const SaveRequestScreen = lazy(() => import("./screens/Clients").then((m) => ({ default: m.SaveRequestScreen })));

type Phase = "loading" | "open" | "join" | "ready" | "suspended";

// ── Тосты ───────────────────────────────────────────────────────────
function Toasts() {
  const { toasts } = useApp();
  const colors: Record<string, string> = {
    info: "bg-primary text-white",
    ok: "bg-emerald-600 text-white",
    warn: "bg-amber-500 text-white",
    err: "bg-rose-600 text-white",
  };
  return (
    <div role="status" aria-live="polite" className="fixed left-0 right-0 bottom-24 z-50 flex flex-col items-center gap-2 px-4 pointer-events-none">
      <AnimatePresence>
        {toasts.map((tt) => (
          <motion.div
            key={tt.id}
            initial={{ opacity: 0, y: 16, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.96 }}
            className={"max-w-[460px] w-fit text-center text-sm font-semibold px-4 py-2.5 rounded-2xl shadow-lg2 " + (colors[tt.kind] || colors.info)}
          >
            {tt.text}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

// ── Заголовки экранов ───────────────────────────────────────────────
function titleKeyFor(route: Route): string | null {
  switch (route.name) {
    case "home":
    case "agencies":
    case "myAgencies":
      return null;
    case "mlsPool":
      return "mlsPoolTitle";
    case "mlsBrowse":
      return "mlsBaseTitle";
    case "toolSheets":
      return "sheetsTitle";
    case "toolFileImport":
      return "baseImportTitle";
    case "toolExcel":
      return "excelTitle";
    case "toolMassImport":
      return "tgImportTitle";
    case "toolWatch":
      return "tgWatchTitle";
    case "profile":
      return "profile";
    case "settings":
      return "settings";
    case "agencyCreate":
      return "createAgency";
    case "agencyManage":
      return "manageAgency";
    case "agencyObjects":
      return "agencyObjects";
    case "agencyObjectDetail":
      return "apartment";
    case "addObject":
      return "addObject";
    case "search":
      return "findObject";
    case "objectList":
      return route.titleKey;
    case "database":
      return "myDatabase";
    case "duplicates":
      return "duplicatesBtn";
    case "objectDetail":
      return "apartment";
    case "objectEdit":
      return "edit";
    case "archive":
      return "archive";
    case "team":
      return "team";
    case "invites":
      return "invites";
    case "analytics":
      return "analytics";
    case "agentDetail":
      return route.agentName;
    case "clients":
      return "clientsTitle";
    case "clientDetail":
      return "clientCard";
    case "clientMatches":
      return "matchesForClient";
    case "matches":
      return "matchesTitle";
    case "saveRequest":
      return "saveAsRequest";
  }
}

function RouteView({ route }: { route: Route }) {
  switch (route.name) {
    case "home":
      return <HomeScreen />;
    case "profile":
      return <ProfileScreen />;
    case "settings":
      return <SettingsScreen />;
    case "agencies":
      return <AgenciesScreen />;
    case "myAgencies":
      return <MyAgenciesScreen />;
    case "mlsPool":
      return <MlsPoolScreen />;
    case "mlsBrowse":
      return <MlsBrowseScreen />;
    case "toolSheets":
      return <ToolSheetsScreen />;
    case "toolFileImport":
      return <ToolFileImportScreen />;
    case "toolExcel":
      return <ToolExcelScreen />;
    case "toolMassImport":
      return <ToolMassImportScreen />;
    case "toolWatch":
      return <ToolWatchScreen />;
    case "agencyCreate":
      return <AgencyCreateScreen />;
    case "agencyManage":
      return <AgencyManageScreen id={route.id} />;
    case "agencyObjects":
      return <AgencyObjectsScreen id={route.id} />;
    case "agencyObjectDetail":
      return <AgencyObjectDetailScreen obj={route.obj} agencyId={route.agencyId} />;
    case "addObject":
      return <AddObjectScreen />;
    case "search":
      return <SearchScreen />;
    case "objectList":
      return <ObjectList params={route.params} allowSaveRequest={route.titleKey === "findObject"} />;
    case "database":
      return <DatabaseScreen />;
    case "duplicates":
      return <DuplicatesScreen />;
    case "objectDetail":
      return <ObjectDetailScreen id={route.id} />;
    case "objectEdit":
      return <ObjectEditScreen obj={route.obj} />;
    case "archive":
      return <ArchiveScreen />;
    case "team":
      return <TeamScreen />;
    case "invites":
      return <InvitesScreen />;
    case "analytics":
      return <AnalyticsScreen />;
    case "agentDetail":
      return <AgentDetailScreen userId={route.userId} agentName={route.agentName} />;
    case "clients":
      return <ClientsScreen />;
    case "clientDetail":
      return <ClientDetailScreen id={route.id} />;
    case "clientMatches":
      return <ClientMatchesScreen id={route.id} />;
    case "matches":
      return <MatchesScreen />;
    case "saveRequest":
      return <SaveRequestScreen criteria={route.criteria} />;
  }
}

// ── Нижняя навигация + плавающая кнопка ─────────────────────────────
function BottomTabs() {
  const { t, user } = useApp();
  const nav = useNav();
  const role = user?.role;
  const rootName = nav.stack[0].name;

  if (role === "superadmin") {
    const tabs: { route: Route; icon: JSX.Element; label: string; key: string }[] = [
      { route: { name: "agencies" }, icon: <Building2 size={22} />, label: t("agenciesTab"), key: "agencies" },
      { route: { name: "myAgencies" }, icon: <Briefcase size={22} />, label: t("myAgenciesTab"), key: "myAgencies" },
      { route: { name: "mlsPool" }, icon: <Layers size={22} />, label: t("mlsTab"), key: "mlsPool" },
      { route: { name: "settings" }, icon: <SettingsIcon size={22} />, label: t("settings"), key: "settings" },
      { route: { name: "profile" }, icon: <User size={22} />, label: t("profile"), key: "profile" },
    ];
    return (
      <nav className="fixed bottom-0 left-0 right-0 z-40 glass border-t border-line px-6 pb-[calc(8px+env(safe-area-inset-bottom,0px))] pt-2">
        <div className="max-w-[560px] mx-auto flex justify-around">
          {tabs.map((tb) => (
            <TabButton key={tb.key} active={rootName === tb.route.name} icon={tb.icon} label={tb.label} onClick={() => nav.resetTo(tb.route)} />
          ))}
        </div>
      </nav>
    );
  }

  const left: { route: Route; icon: JSX.Element; label: string }[] = [
    { route: { name: "home" }, icon: <Home size={22} />, label: t("home") },
    { route: { name: "search" }, icon: <Search size={22} />, label: t("findObject") },
  ];
  const right: { route: Route; icon: JSX.Element; label: string }[] = [
    { route: { name: "database" }, icon: <Database size={22} />, label: t("myDatabase") },
    { route: { name: "profile" }, icon: <User size={22} />, label: t("profile") },
  ];
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 glass border-t border-line px-3 pb-[calc(8px+env(safe-area-inset-bottom,0px))] pt-2">
      <div className="max-w-[560px] mx-auto flex items-end justify-between">
        {left.map((tb, i) => (
          <TabButton key={i} active={rootName === tb.route.name} icon={tb.icon} label={tb.label} onClick={() => nav.resetTo(tb.route)} />
        ))}
        <button
          onClick={() => nav.push({ name: "addObject" })}
          className="-mt-7 w-14 h-14 rounded-2xl text-white flex items-center justify-center shadow-glow active:scale-95 transition shrink-0"
          style={{ background: "var(--grad)" }}
          aria-label={t("addObject")}
        >
          <Plus size={26} />
        </button>
        {right.map((tb, i) => (
          <TabButton key={i} active={rootName === tb.route.name} icon={tb.icon} label={tb.label} onClick={() => nav.resetTo(tb.route)} />
        ))}
      </div>
    </nav>
  );
}

function TabButton({ active, icon, label, onClick }: { active: boolean; icon: JSX.Element; label: string; onClick: () => void }) {
  return (
    <button
      onClick={() => {
        if (!active) haptic();
        onClick();
      }}
      className={"flex flex-col items-center gap-1 px-2 py-1 min-w-[58px] cursor-pointer transition-colors duration-200 active:scale-95 " + (active ? "text-primary" : "text-muted")}
    >
      <span className={"flex items-center justify-center w-11 h-7 rounded-full transition-colors duration-200 " + (active ? "bg-primary-soft" : "")}>
        {icon}
      </span>
      <span className="text-[10.5px] font-bold leading-none truncate max-w-[64px]">{label}</span>
    </button>
  );
}

// ── Оболочка (после входа) ──────────────────────────────────────────
function Shell() {
  const { t, user } = useApp();
  const { exitToPlatform } = useActing();
  const nav = useNav();
  const acting = user?.real_role === "superadmin" && !!user?.acting_as_agency_id;
  const depth = nav.stack.length;
  const route = nav.current;
  const tkey = titleKeyFor(route);
  const showBack = depth > 1;

  // «В сети»: пока приложение открыто и видимо, периодически шлём heartbeat —
  // так владелец агентства видит статус сотрудника «в сети» и точное время
  // активности. Пинг раз в минуту + сразу при возврате во вкладку.
  useEffect(() => {
    const ping = () => {
      if (document.visibilityState === "visible") {
        api("/api/v1/auth/heartbeat", { method: "POST" });
      }
    };
    ping();
    const id = window.setInterval(ping, 60000);
    document.addEventListener("visibilitychange", ping);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", ping);
    };
  }, []);

  // Кнопка «Назад» Telegram.
  useEffect(() => {
    const bb = tg?.BackButton;
    if (!bb) return;
    try {
      if (showBack) bb.show();
      else bb.hide();
    } catch {
      /* noop */
    }
    const handler = () => nav.pop();
    try {
      bb.onClick(handler);
    } catch {
      /* noop */
    }
    return () => {
      try {
        bb.offClick(handler);
      } catch {
        /* noop */
      }
    };
  }, [showBack, nav]);

  // Жест «назад»: свайп от КРАЯ экрана внутрь возвращает на шаг назад.
  // От левого края — вправо, от правого края — влево. Старт засекаем только у
  // самого края (≤28px), чтобы не конфликтовать с горизонтальными свайпами
  // внутри контента (переключение вкладок в «Базе»).
  const edgeSwipe = useRef<{ x: number; y: number; t: number; edge: "left" | "right" } | null>(null);
  const onTouchStart = (e: React.TouchEvent) => {
    const p = e.touches[0];
    const w = window.innerWidth;
    const edge: "left" | "right" | null =
      p.clientX <= 28 ? "left" : p.clientX >= w - 28 ? "right" : null;
    edgeSwipe.current = edge ? { x: p.clientX, y: p.clientY, t: Date.now(), edge } : null;
  };
  const onTouchEnd = (e: React.TouchEvent) => {
    const s = edgeSwipe.current;
    edgeSwipe.current = null;
    if (!s || !showBack) return;
    const p = e.changedTouches[0];
    const dx = p.clientX - s.x;
    const dy = p.clientY - s.y;
    if (Date.now() - s.t >= 700 || Math.abs(dx) < 65 || Math.abs(dx) < Math.abs(dy) * 1.8) return;
    // От левого края тянем вправо (dx>0), от правого — влево (dx<0).
    if ((s.edge === "left" && dx > 0) || (s.edge === "right" && dx < 0)) {
      haptic();
      nav.pop();
    }
  };

  return (
    <div className="min-h-screen pb-28" onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>
      <div className="max-w-[560px] mx-auto px-3.5 pt-3.5">
        {/* Баннер acting-режима: владелец платформы внутри своего агентства */}
        {acting && (
          <button
            onClick={async () => {
              await exitToPlatform();
              nav.resetTo({ name: "agencies" });
            }}
            className="w-full mb-3 rounded-xl2 px-3.5 py-2.5 text-left text-[13px] font-bold text-white shadow-soft active:scale-[.99] transition"
            style={{ background: "var(--grad)" }}
          >
            {t("actingBanner").replace("{name}", user?.acting_as_agency_name || "")}
            <span className="block text-[12px] font-semibold opacity-90 underline">
              {t("exitToPlatform")}
            </span>
          </button>
        )}
        {/* Шапка */}
        <header className="flex items-center gap-3 min-h-[40px] mb-3">
          {showBack ? (
            <span className="text-[19px] font-extrabold tracking-tight">{tkey ? t(tkey) : ""}</span>
          ) : (
            <div className="flex items-center gap-2.5">
              <span className="w-8 h-8 rounded-[10px] flex items-center justify-center text-white shadow-glow" style={{ background: "var(--grad)" }}>
                <Building2 size={18} />
              </span>
              <span className="text-[18px] font-extrabold tracking-tight">
                Realty <span className="text-primary">AI</span>
              </span>
            </div>
          )}
        </header>

        {/* Контент с анимацией */}
        <AnimatePresence mode="wait">
          <motion.div
            key={depth + ":" + route.name}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.22 }}
          >
            <Suspense fallback={<div className="py-12"><Spinner /></div>}>
              <RouteView route={route} />
            </Suspense>
          </motion.div>
        </AnimatePresence>
      </div>
      <BottomTabs />
    </div>
  );
}

// ── Экран «Откройте в Telegram» ─────────────────────────────────────
function OpenInTelegram() {
  const { t } = useApp();
  const [ok, setOk] = useState<boolean | null>(null);
  useEffect(() => {
    fetch("/health")
      .then((r) => r.json())
      .then((d) => setOk(d.database === "connected"))
      .catch(() => setOk(false));
  }, []);
  return (
    <div className="max-w-[560px] mx-auto px-4 pt-14 animate-fade-up">
      <div className="flex flex-col items-center text-center mb-5">
        <span className="w-16 h-16 rounded-[20px] flex items-center justify-center text-white shadow-glow mb-3" style={{ background: "var(--grad)" }}>
          <Building2 size={30} />
        </span>
        <span className="text-[24px] font-extrabold tracking-tight">
          Realty <span className="text-primary">AI</span>
        </span>
      </div>
      <div className={"rounded-[14px] px-4 py-3 text-sm font-semibold text-center " + (ok ? "bg-emerald-500/10 text-emerald-600" : "bg-amber-500/10 text-amber-600")}>
        {ok == null ? t("loading") : ok ? t("backendOk") : t("backendErr")}
      </div>
      <p className="text-muted text-sm mt-3 text-center">{t("openInTg")}</p>
    </div>
  );
}

// ── Экран вступления по коду ────────────────────────────────────────
function JoinScreen({ prefill, onAuth }: { prefill: string; onAuth: (r: AuthResponse) => void }) {
  const { t, toast } = useApp();
  const [code, setCode] = useState(prefill || "");
  const [busy, setBusy] = useState(false);
  const triedAuto = useRef(false);

  async function join(c: string) {
    const v = c.trim();
    if (!v) return;
    setBusy(true);
    const r = await api<AuthResponse>("/api/v1/invites/redeem", { method: "POST", body: { init_data: getInitData(), code: v } });
    setBusy(false);
    if (r.ok && r.data) onAuth(r.data);
    else toast(t("loginFail") + errText(r.data, r.status), "err");
  }

  useEffect(() => {
    if (prefill && !triedAuto.current) {
      triedAuto.current = true;
      join(prefill);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefill]);

  return (
    <div className="max-w-[560px] mx-auto px-4 pt-10 animate-fade-up">
      {/* Первое впечатление нового сотрудника: крупный брендовый блок. */}
      <div className="flex flex-col items-center text-center mb-5">
        <span className="w-16 h-16 rounded-[20px] flex items-center justify-center text-white shadow-glow mb-3" style={{ background: "var(--grad)" }}>
          <Building2 size={30} />
        </span>
        <span className="text-[24px] font-extrabold tracking-tight">
          Realty <span className="text-primary">AI</span>
        </span>
      </div>
      <div className="rounded-[14px] px-4 py-3 text-sm bg-primary-soft text-primary mb-3 text-center">{t("notInAgency")}</div>
      <Card>
        <Field label={t("joinCodeLabel")}>
          <Input value={code} onChange={(e) => setCode(e.target.value)} />
        </Field>
        <Button full className="mt-4" disabled={busy} onClick={() => join(code)}>
          {busy ? t("joinChecking") : t("joinBtn")}
        </Button>
      </Card>
    </div>
  );
}

// ── Корень ──────────────────────────────────────────────────────────
export function App() {
  const { setAuth, setSettings, user, subscriptionActive, clearAuth, toast, t } = useApp();
  const [phase, setPhase] = useState<Phase>("loading");
  const [startParam, setStartParam] = useState("");

  async function loadSettingsIfNeeded(role: string) {
    if (role === "agency_admin" || role === "agent") {
      const r = await api<AgencySettings>("/api/v1/agency/settings");
      if (r.ok && r.data) setSettings(r.data);
    } else {
      // Суперадмин на платформе: чужие настройки агентства не нужны (могли
      // остаться от acting-сессии) — сбрасываем.
      setSettings(null);
    }
  }

  // refresh-пропуск держим только в памяти (не в localStorage) — как и access-токен.
  const refreshTokenRef = useRef<string | null>(null);
  // Текущее личное агентство (acting): нужно, чтобы тихое продление сессии не
  // выкидывало владельца из агентства обратно на платформу.
  const actingAgencyRef = useRef<number | null>(null);

  async function applyAuth(data: AuthResponse) {
    setAuth(data.access_token, data.user, data.subscription_active ?? null);
    refreshTokenRef.current = data.refresh_token ?? refreshTokenRef.current;
    actingAgencyRef.current = data.user.acting_as_agency_id ?? null;
    await loadSettingsIfNeeded(data.user.role);
    if ((data.user.role === "agency_admin" || data.user.role === "agent") && data.subscription_active === false) {
      setPhase("suspended");
    } else {
      setPhase("ready");
    }
  }

  // Войти в своё личное агентство (acting): получить сессию главного админа.
  async function enterAgency(id: number): Promise<boolean> {
    const r = await api<AuthResponse>(`/api/v1/agencies/${id}/enter`, { method: "POST" });
    if (r.ok && r.data) {
      await applyAuth(r.data);
      return true;
    }
    toast(errText(r.data, r.status) || t("loginFail"), "err");
    return false;
  }

  // Выйти из агентства обратно на платформу (роль суперадмина). Обновляем сессию
  // БЕЗ act_as — сервер вернёт обычную сессию владельца.
  async function exitToPlatform(): Promise<void> {
    const rt = refreshTokenRef.current;
    if (rt) {
      const r = await api<AuthResponse>("/api/v1/auth/refresh", {
        method: "POST",
        body: { refresh_token: rt },
      });
      if (r.ok && r.data) {
        await applyAuth(r.data);
        return;
      }
    }
    // Запасной путь: вход по initData (вернёт суперадмина).
    const fresh = getInitData();
    if (fresh) {
      const r = await api<AuthResponse>("/api/v1/auth/telegram", {
        method: "POST",
        body: { init_data: fresh },
      });
      if (r.ok && r.data) await applyAuth(r.data);
    }
  }

  useEffect(() => {
    tgReady();
    const initData = getInitData();
    const sp = getStartParam();
    setStartParam(sp);

    // Тихий перелогин: если пропуск истечёт во время работы, API-клиент сам
    // запросит новый через Telegram и повторит запрос (см. api.ts). Прямой
    // fetch (без обёртки api) — чтобы не было зацикливания на 401.
    setReauthHandler(async () => {
      // Сначала пробуем тихо продлить сессию по refresh-пропуску (сервер умеет
      // это через /auth/refresh, без повторной проверки initData). Это и есть
      // починка «вылетов» каждые 1–2 часа (находка H7).
      const rt = refreshTokenRef.current;
      if (rt) {
        try {
          const res = await fetch("/api/v1/auth/refresh", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              refresh_token: rt,
              // Если владелец сейчас внутри своего агентства — сохраняем контекст.
              act_as_agency_id: actingAgencyRef.current,
            }),
          });
          if (res.ok) {
            const data: AuthResponse = await res.json();
            setAuth(data.access_token, data.user, data.subscription_active ?? null);
            refreshTokenRef.current = data.refresh_token ?? refreshTokenRef.current;
            actingAgencyRef.current = data.user.acting_as_agency_id ?? null;
            return data.access_token;
          }
        } catch {
          // упадём в запасной путь ниже
        }
      }
      // Запасной путь: повторный вход по initData (если refresh-пропуска нет
      // или он больше не действует).
      const fresh = getInitData();
      if (!fresh) return null;
      try {
        const res = await fetch("/api/v1/auth/telegram", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ init_data: fresh }),
        });
        if (!res.ok) return null;
        const data: AuthResponse = await res.json();
        setAuth(data.access_token, data.user, data.subscription_active ?? null);
        refreshTokenRef.current = data.refresh_token ?? refreshTokenRef.current;
        actingAgencyRef.current = data.user.acting_as_agency_id ?? null;
        return data.access_token;
      } catch {
        return null;
      }
    });

    if (!initData) {
      setPhase("open");
      return;
    }
    (async () => {
      const r = await api<AuthResponse>("/api/v1/auth/telegram", { method: "POST", body: { init_data: initData } });
      if (r.ok && r.data) {
        await applyAuth(r.data);
      } else if (r.status === 403) {
        setPhase("join");
      } else {
        // Покажем экран входа по коду как запасной (или открыть в Telegram).
        setPhase(initData ? "join" : "open");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Если владельца разлогинили (передача прав) — вернуться к экрану входа.
  useEffect(() => {
    if (phase === "ready" && !user) setPhase("open");
  }, [user, phase]);

  if (phase === "loading") {
    return (
      <div className="pt-24">
        <Spinner />
      </div>
    );
  }
  if (phase === "open") return <OpenInTelegram />;
  if (phase === "join") return <JoinScreen prefill={startParam} onAuth={applyAuth} />;
  if (phase === "suspended") {
    return (
      <div className="max-w-[560px] mx-auto px-3.5 pt-5">
        <SuspendedScreen />
      </div>
    );
  }

  const initialRoute: Route = user?.role === "superadmin" ? { name: "agencies" } : { name: "home" };
  return (
    <NavProvider initial={initialRoute}>
      <ActingProvider value={{ enterAgency, exitToPlatform }}>
        <Shell />
      </ActingProvider>
      <Toasts />
    </NavProvider>
  );
}
