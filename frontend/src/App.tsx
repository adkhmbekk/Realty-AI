import React, { lazy, Suspense, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Briefcase, Building2, Home, Layers, Mail, Plus, Search, Settings as SettingsIcon, User, Users } from "lucide-react";
import { useApp } from "./store";
import { NavProvider, PaneActiveContext, Pane, Route, useNav } from "./nav";
import { ActingProvider, useActing } from "./acting";
import { api, apiUrl, errText, extraHeaders, getLastFetchError, setReauthHandler } from "./api";
import { tg, tgReady, getInitData, getStartParam, haptic, isNativeApp } from "./telegram";
import { saveSession, loadSession, clearSession } from "./session";
import { getProviderToken } from "./nativeAuth";
import type { AuthResponse, AgencySettings } from "./types";
import { Button, Card, Field, Input, Spinner } from "./components/ui";
import { HomeScreen } from "./screens/Home";
import { ProfileScreen, SuspendedScreen } from "./screens/Profile";
import { PersonalApp, PersonalSettingsScreen, PersonalProfileScreen } from "./screens/Personal";
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
const PlatformUsersScreen = lazy(() => import("./screens/PlatformUsers").then((m) => ({ default: m.PlatformUsersScreen })));
const PlatformUserDetailScreen = lazy(() => import("./screens/PlatformUsers").then((m) => ({ default: m.PlatformUserDetailScreen })));
const AgencyCreateScreen = lazy(() => import("./screens/Superadmin").then((m) => ({ default: m.AgencyCreateScreen })));
const AgencyManageScreen = lazy(() => import("./screens/Superadmin").then((m) => ({ default: m.AgencyManageScreen })));
const AgencyObjectsScreen = lazy(() => import("./screens/Superadmin").then((m) => ({ default: m.AgencyObjectsScreen })));
const AgencyObjectDetailScreen = lazy(() => import("./screens/Apartments").then((m) => ({ default: m.AgencyObjectDetailScreen })));
const MlsObjectDetailScreen = lazy(() => import("./screens/Apartments").then((m) => ({ default: m.MlsObjectDetailScreen })));
const MlsPoolScreen = lazy(() => import("./screens/Superadmin").then((m) => ({ default: m.MlsPoolScreen })));
const MyAgenciesScreen = lazy(() => import("./screens/Superadmin").then((m) => ({ default: m.MyAgenciesScreen })));
const PersonalAgenciesScreen = lazy(() => import("./screens/Superadmin").then((m) => ({ default: m.PersonalAgenciesScreen })));
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

type Phase = "loading" | "open" | "join" | "personal" | "ready" | "suspended" | "reconnect" | "login";

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
    case "myAgencies":
      return null;
    case "agencies":
      return "financesTab";
    case "platformUsers":
      return "usersTab";
    case "platformUserDetail":
      return "usersTab";
    case "personalAgencies":
      return "myAgenciesTitle";
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
    case "mlsObjectDetail":
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
  const { user } = useApp();
  // Суперадмин — тоже юзер: его личные Настройки/Профиль идентичны юзерским.
  // (Внутри агентства он acting=agency_admin → показываем агентские экраны.)
  const pureSuper = user?.role === "superadmin";
  switch (route.name) {
    case "home":
      return <HomeScreen />;
    case "profile":
      return pureSuper ? <PersonalProfileScreen /> : <ProfileScreen />;
    case "settings":
      return pureSuper ? <PersonalSettingsScreen /> : <SettingsScreen />;
    case "agencies":
      return <AgenciesScreen />;
    case "platformUsers":
      return <PlatformUsersScreen />;
    case "platformUserDetail":
      return <PlatformUserDetailScreen id={route.id} />;
    case "myAgencies":
      return <MyAgenciesScreen />;
    case "personalAgencies":
      return <PersonalAgenciesScreen />;
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
    case "mlsObjectDetail":
      return <MlsObjectDetailScreen item={route.item} />;
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
      return <ClientMatchesScreen clientId={route.clientId} requestId={route.requestId} label={route.label} />;
    case "matches":
      return <MatchesScreen />;
    case "saveRequest":
      return <SaveRequestScreen criteria={route.criteria} />;
  }
}

// ── Нижняя навигация + плавающая кнопка ─────────────────────────────
// Открыта ли экранная клавиатура (visualViewport заметно ниже окна). Нужно, чтобы
// прятать нижнюю панель — иначе она «всплывает» и ложится поверх клавиатуры.
function useKeyboardOpen() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const onResize = () => setOpen(window.innerHeight - vv.height > 160);
    vv.addEventListener("resize", onResize);
    onResize();
    return () => vv.removeEventListener("resize", onResize);
  }, []);
  return open;
}

function BottomTabs() {
  const { t, user } = useApp();
  const nav = useNav();
  const kb = useKeyboardOpen();
  const role = user?.role;
  // Подсветка таба — по ТЕКУЩЕМУ маршруту (а не по «последнему выбранному»):
  // иначе при переходе в «Добавить объект» горела бы вкладка, откуда пришли.
  const curName = nav.current?.name;
  if (kb) return null;

  if (role === "superadmin") {
    // Суперадмин работает как юзер (личный хаб), но видит больше: нижняя панель —
    // Главная / Настройки / Профиль. «Главная» = хаб (Финансы, Мои агентства,
    // Пользователи, Общая база) — экран myAgencies.
    const tabs: { route: Route; icon: JSX.Element; label: string; key: string }[] = [
      { route: { name: "myAgencies" }, icon: <Home size={22} />, label: t("home"), key: "myAgencies" },
      { route: { name: "settings" }, icon: <SettingsIcon size={22} />, label: t("settings"), key: "settings" },
      { route: { name: "profile" }, icon: <User size={22} />, label: t("profile"), key: "profile" },
    ];
    return (
      <nav className="shrink-0 z-40 glass border-t border-line px-6 pb-[calc(8px+env(safe-area-inset-bottom,0px))] pt-2">
        <div className="max-w-[560px] mx-auto flex justify-around">
          {tabs.map((tb) => (
            <TabButton key={tb.key} active={curName === tb.route.name} icon={tb.icon} label={tb.label} onClick={() => nav.switchTab(tb.route)} />
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
    { route: { name: "settings" }, icon: <SettingsIcon size={22} />, label: t("settings") },
    { route: { name: "profile" }, icon: <User size={22} />, label: t("profile") },
  ];
  return (
    <nav className="shrink-0 z-40 glass border-t border-line px-3 pb-[calc(8px+env(safe-area-inset-bottom,0px))] pt-2">
      <div className="max-w-[560px] mx-auto flex items-end justify-between">
        {left.map((tb, i) => (
          <TabButton key={i} active={curName === tb.route.name} icon={tb.icon} label={tb.label} onClick={() => nav.switchTab(tb.route)} />
        ))}
        <button
          onClick={() => nav.pushTransient({ name: "addObject" })}
          className="-mt-7 w-14 h-14 rounded-2xl text-white flex items-center justify-center shadow-glow active:scale-95 transition shrink-0"
          style={{ background: "var(--grad)" }}
          aria-label={t("addObject")}
        >
          <Plus size={26} />
        </button>
        {right.map((tb, i) => (
          <TabButton key={i} active={curName === tb.route.name} icon={tb.icon} label={tb.label} onClick={() => nav.switchTab(tb.route)} />
        ))}
      </div>
    </nav>
  );
}

// Хост одной живой страницы: собственный контейнер скролла, собственное состояние
// (никогда не размонтируется, пока в стеке), собственная анимация. Неактивные —
// display:none: страница полностью убрана из отрисовки и не может «просвечивать»
// поверх активной. Позиция скролла у каждой страницы своя: сохраняем её при
// прокрутке и восстанавливаем при возврате на страницу (не сброс, а именно
// сохранение). PaneActiveContext даёт экрану знать, что он снова виден.
// React.memo: панели живут постоянно (keep-alive), и при ЛЮБОЙ навигации шелл
// перерисовывается. Без memo это перерисовывало бы ВСЕ смонтированные экраны
// (включая скрытые) на каждый переход (FE1). pane-объекты стабильны по ссылке,
// поэтому memo перерисовывает только ту панель, у которой изменился active.
const PageHost = React.memo(function PageHost({ pane, active }: { pane: Pane; active: boolean }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const savedTop = useRef(0);
  const prevActive = useRef(active);
  useLayoutEffect(() => {
    const el = scrollRef.current;
    // Восстанавливаем скролл при переходе «скрыт → виден» (свой у каждой страницы).
    if (el && active && !prevActive.current) el.scrollTop = savedTop.current;
    prevActive.current = active;
  });
  return (
    <div
      ref={scrollRef}
      aria-hidden={!active}
      onScroll={(e) => {
        savedTop.current = e.currentTarget.scrollTop;
      }}
      className="absolute inset-0 overflow-y-auto overflow-x-hidden overscroll-contain"
      style={{ display: active ? undefined : "none", WebkitOverflowScrolling: "touch" }}
    >
      <motion.div
        className="max-w-[560px] mx-auto px-3.5 py-3.5"
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.15, ease: "easeOut" }}
      >
        <PaneActiveContext.Provider value={active}>
          <Suspense fallback={<div className="py-12"><Spinner /></div>}>
            <RouteView route={pane.route} />
          </Suspense>
        </PaneActiveContext.Provider>
      </motion.div>
    </div>
  );
});

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
// Heartbeat присутствия: пока приложение открыто и видимо — пинг раз в минуту
// (+ сразу и при возврате во вкладку). enabled=false — молчим (неавторизованные
// фазы). ВАЖНО: работает и в личном пространстве, и внутри агентства — иначе
// профиль-визиты не видны в списке юзеров, а человек не показывается «в сети».
function useHeartbeat(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
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
  }, [enabled]);
}

function Shell() {
  const { t, user } = useApp();
  const nav = useNav();
  const depth = nav.stack.length;
  const route = nav.current;
  const tkey = titleKeyFor(route);
  const showBack = depth > 1;

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
    <div
      className="fixed left-0 right-0 bottom-0 flex flex-col"
      style={{ top: "var(--tg-top-inset, 0px)" }}
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
    >
      {/* Верхняя область (шапка) — фиксирована, не участвует в скролле страниц.
          Баннер acting «вы в агентстве… выйти на платформу» убран: возврат теперь
          через свитчер/кнопку «В личный кабинет» в профиле. */}
      <div className="shrink-0 w-full max-w-[560px] mx-auto px-3.5 pt-3.5">
        {/* Шапка */}
        <header className="flex items-center gap-2.5 min-h-[40px] mb-2">
          {/* Логотип-бейдж — на КАЖДОМ экране (левый верхний угол), чтобы ни одно окно
              не выглядело «неполноценным». Рядом: на главных экранах — «Realty AI»,
              на вложенных — заголовок страницы (контекст «где я» не теряется). */}
          <span className="w-8 h-8 rounded-[10px] flex items-center justify-center text-white shadow-glow shrink-0" style={{ background: "var(--grad)" }}>
            <Building2 size={18} />
          </span>
          {showBack ? (
            <span className="text-[19px] font-extrabold tracking-tight truncate">{tkey ? t(tkey) : ""}</span>
          ) : (
            <span className="text-[18px] font-extrabold tracking-tight">
              Realty <span className="text-primary">AI</span>
            </span>
          )}
        </header>
      </div>

      {/* Область страниц: каждая страница — живой, независимый экран со своим скроллом.
          Все смонтированы (состояние/скролл сохраняются), видна только активная. */}
      <div className="relative flex-1 min-h-0 overflow-hidden">
        {nav.panes.map((pane) => (
          <PageHost key={pane.id} pane={pane} active={pane.id === nav.activePaneId} />
        ))}
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
    fetch(apiUrl("/health"))
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

// ── Экран входа в нативном приложении (вне Telegram) ──────────────────
// Показывается, когда мы вне Telegram и действующей сессии нет: вход через
// Google/Apple. Сам SDK-шаг (получение токена провайдера) подключается в Фазе 3
// (Capacitor-плагины); до этого кнопки показывают подсказку через toast.
function NativeLoginScreen({
  onSignIn,
  onTelegram,
}: {
  onSignIn: (p: "google" | "apple") => Promise<string | null>;
  onTelegram: () => Promise<string | null>;
}) {
  const [busy, setBusy] = useState<null | "google" | "apple" | "telegram">(null);
  const [err, setErr] = useState<string | null>(null);
  const goTelegram = async () => {
    setBusy("telegram");
    setErr("Открываю Telegram… подтвердите вход в боте.");
    try {
      setErr(await onTelegram());
    } catch (e: any) {
      setErr("сбой обработчика: " + (e?.message || String(e)));
    } finally {
      setBusy(null);
    }
  };
  const go = async (p: "google" | "apple") => {
    setBusy(p);
    setErr("запуск…");
    try {
      const m = await onSignIn(p);
      setErr(m);
    } catch (e: any) {
      setErr("сбой обработчика: " + (e?.message || String(e)));
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="max-w-[560px] mx-auto px-4 pt-16 animate-fade-up">
      <div className="flex flex-col items-center text-center mb-8">
        <span className="w-16 h-16 rounded-[20px] flex items-center justify-center text-white shadow-glow mb-3" style={{ background: "var(--grad)" }}>
          <Building2 size={30} />
        </span>
        <span className="text-[24px] font-extrabold tracking-tight">
          Realty <span className="text-primary">AI</span>
        </span>
        <p className="text-muted text-sm mt-2">CRM + MLS для агентств недвижимости</p>
      </div>
      {err && (
        <div className="mb-3 rounded-xl bg-rose-500/10 text-rose-600 dark:text-rose-400 px-3 py-2 text-[13px] font-semibold break-words">
          {err}
        </div>
      )}
      <div className="space-y-3">
        <button
          onClick={goTelegram}
          disabled={!!busy}
          className="w-full py-3 rounded-xl font-bold text-[15px] text-white cursor-pointer active:scale-[.98] transition disabled:opacity-50"
          style={{ background: "#229ED9" }}
        >
          {busy === "telegram" ? "…" : "Войти через Telegram"}
        </button>
        <button
          onClick={() => go("google")}
          disabled={!!busy}
          className="w-full py-3 rounded-xl font-bold text-[15px] text-white cursor-pointer active:scale-[.98] transition disabled:opacity-50"
          style={{ background: "var(--grad)" }}
        >
          {busy === "google" ? "…" : "Войти через Google"}
        </button>
        <button
          onClick={() => go("apple")}
          disabled={!!busy}
          className="w-full py-3 rounded-xl font-bold text-[15px] cursor-pointer active:scale-[.98] transition disabled:opacity-50 bg-black text-white dark:bg-white dark:text-black"
        >
          {busy === "apple" ? "…" : "Войти через Apple"}
        </button>
      </div>
    </div>
  );
}

// ── Экран «нет связи» при запуске ─────────────────────────────────────
// Показывается, когда первичный вход не удался из-за связи (а НЕ из-за того,
// что человек не в агентстве). Само-восстанавливается: пока открыт, тихо
// повторяет вход каждые 6 c — вернулась связь, приложение войдёт само.
function ReconnectScreen({ onRetry }: { onRetry: () => void }) {
  const { t } = useApp();
  useEffect(() => {
    const id = setInterval(onRetry, 6000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      <Card>
        <div className="text-[16px] font-extrabold text-center">{t("connLostTitle")}</div>
        <p className="text-muted text-sm mt-2 text-center">{t("connLostMsg")}</p>
        <div className="flex justify-center mt-3"><Spinner /></div>
        <Button full className="mt-3" onClick={onRetry}>{t("retryBtn")}</Button>
      </Card>
    </div>
  );
}

// ── Экран приветствия для нового человека (ещё без агентства) ─────────
// Два пути: СОЗДАТЬ своё агентство (саморегистрация) или ВОЙТИ по коду
// приглашения. Если пришли по ссылке-приглашению (есть код) — сразу режим кода.
function WelcomeScreen({ prefill, onAuth }: { prefill: string; onAuth: (r: AuthResponse) => void }) {
  const { t, toast } = useApp();
  const [mode, setMode] = useState<"choose" | "create" | "code">(prefill ? "code" : "choose");
  const [code, setCode] = useState(prefill || "");
  const [busy, setBusy] = useState(false);
  const triedAuto = useRef(false);
  // Поля регистрации агентства.
  const [name, setName] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [phone, setPhone] = useState("");

  async function join(c: string) {
    const v = c.trim();
    if (!v) return;
    setBusy(true);
    const r = await api<AuthResponse>("/api/v1/invites/redeem", { method: "POST", body: { init_data: getInitData(), code: v } });
    setBusy(false);
    if (r.ok && r.data) onAuth(r.data);
    else toast(t("loginFail") + errText(r.data, r.status), "err");
  }

  async function register() {
    if (!name.trim()) { toast(t("regNameRequired"), "err"); return; }
    if (!ownerName.trim()) { toast(t("regOwnerRequired"), "err"); return; }
    if (!phone.trim()) { toast(t("regPhoneRequired"), "err"); return; }
    setBusy(true);
    const r = await api<AuthResponse>("/api/v1/agencies/register", {
      method: "POST",
      body: { init_data: getInitData(), name: name.trim(), owner_name: ownerName.trim(), phone: phone.trim() },
    });
    setBusy(false);
    if (r.ok && r.data) onAuth(r.data);
    else toast(errText(r.data, r.status), "err");
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
      <div className="flex flex-col items-center text-center mb-5">
        <span className="w-16 h-16 rounded-[20px] flex items-center justify-center text-white shadow-glow mb-3" style={{ background: "var(--grad)" }}>
          <Building2 size={30} />
        </span>
        <span className="text-[24px] font-extrabold tracking-tight">
          Realty <span className="text-primary">AI</span>
        </span>
      </div>

      {mode === "choose" && (
        <>
          <div className="text-center text-[14px] text-muted mb-4">{t("welcomeSub")}</div>
          <button
            onClick={() => setMode("create")}
            className="w-full text-left rounded-xl2 p-4 mb-3 text-white shadow-glow active:scale-[.99] transition"
            style={{ background: "var(--grad)" }}
          >
            <div className="flex items-center gap-3">
              <span className="w-11 h-11 rounded-xl bg-white/20 flex items-center justify-center shrink-0"><Plus size={22} /></span>
              <div className="min-w-0">
                <div className="text-[16px] font-extrabold">{t("welcomeCreateAgency")}</div>
                <div className="text-[12.5px] opacity-90">{t("welcomeCreateSub")}</div>
              </div>
            </div>
          </button>
          <button
            onClick={() => setMode("code")}
            className="w-full text-left rounded-xl2 bg-card border border-line shadow-soft p-4 active:scale-[.99] transition"
          >
            <div className="flex items-center gap-3">
              <span className="w-11 h-11 rounded-xl bg-primary-soft text-primary flex items-center justify-center shrink-0"><Mail size={20} /></span>
              <div className="min-w-0">
                <div className="text-[16px] font-extrabold">{t("welcomeHaveCode")}</div>
                <div className="text-[12.5px] text-muted">{t("welcomeHaveCodeSub")}</div>
              </div>
            </div>
          </button>
        </>
      )}

      {mode === "create" && (
        <Card>
          <div className="text-[16px] font-extrabold mb-1">{t("regTitle")}</div>
          <div className="text-[13px] text-muted mb-2">{t("regSub")}</div>
          <Field label={t("regName")}>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("regNamePh")} />
          </Field>
          <Field label={t("regOwner")}>
            <Input value={ownerName} onChange={(e) => setOwnerName(e.target.value)} placeholder={t("regOwnerPh")} />
          </Field>
          <Field label={t("regPhone")}>
            <Input inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder={t("regPhonePh")} />
          </Field>
          <Button full className="mt-4" disabled={busy} onClick={register}>
            {busy ? t("joinChecking") : t("regSubmit")}
          </Button>
          <button onClick={() => setMode("choose")} className="w-full mt-3 text-[13px] font-bold text-muted">{t("regBack")}</button>
        </Card>
      )}

      {mode === "code" && (
        <Card>
          <div className="rounded-[14px] px-4 py-3 text-sm bg-primary-soft text-primary mb-3 text-center">{t("notInAgency")}</div>
          <Field label={t("joinCodeLabel")}>
            <Input value={code} onChange={(e) => setCode(e.target.value)} />
          </Field>
          <Button full className="mt-4" disabled={busy} onClick={() => join(code)}>
            {busy ? t("joinChecking") : t("joinBtn")}
          </Button>
          {!prefill && (
            <button onClick={() => setMode("choose")} className="w-full mt-3 text-[13px] font-bold text-muted">{t("regBack")}</button>
          )}
        </Card>
      )}
    </div>
  );
}

// ── Корень ──────────────────────────────────────────────────────────
export function App() {
  const { setAuth, setSettings, user, subscriptionActive, clearAuth, toast, t } = useApp();
  const [phase, setPhase] = useState<Phase>("loading");
  const [startParam, setStartParam] = useState("");

  // Heartbeat присутствия во ВСЕХ авторизованных фазах — и в личном пространстве
  // (personal), и внутри агентства (ready). Раньше он жил только в Shell (ready) →
  // профиль-визиты не отмечались как активность.
  useHeartbeat(phase === "personal" || phase === "ready");

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

  async function applyAuth(data: AuthResponse, opts?: { enterAgency?: boolean }) {
    setAuth(data.access_token, data.user, data.subscription_active ?? null);
    refreshTokenRef.current = data.refresh_token ?? refreshTokenRef.current;
    actingAgencyRef.current = data.user.acting_as_agency_id ?? null;
    // Нативное приложение (вне Telegram): сохраняем сессию, чтобы пережить
    // перезапуск. В Telegram токены живут только в памяти — там повторный вход по
    // initData бесплатный, персист не нужен (и не путает archived-модель).
    if (isNativeApp()) void saveSession(data.access_token, refreshTokenRef.current);
    const u = data.user;
    // Суперадмин — своя платформенная оболочка (агентства/юзеры).
    if (u.role === "superadmin") {
      await loadSettingsIfNeeded(u.role);
      setPhase("ready");
      return;
    }
    // Юзер-центричная модель: участник/личный аккаунт, пока НЕ «вошёл» в
    // агентство, видит личное пространство (хаб). Внутри агентства (после
    // enter/create или acting-контекста) — рабочая оболочка агентства.
    const inAgency = !!opts?.enterAgency || !!u.acting_as_agency_id;
    if (!inAgency) {
      setPhase("personal");
      return;
    }
    await loadSettingsIfNeeded(u.role);
    if ((u.role === "agency_admin" || u.role === "agent") && data.subscription_active === false) {
      setPhase("suspended");
    } else {
      setPhase("ready");
    }
  }

  // Первичный вход при запуске приложения. КЛЮЧЕВОЕ: обрыв связи ≠ «нет
  // агентства». Раньше любой не-200 (включая status 0 — обрыв сети/таймаут
  // туннеля) сваливался в экран «создать агентство», и существующего риелтора
  // выкидывало на регистрацию при секундном моргании интернета. Теперь:
  //   • 200            → входим;
  //   • 403            → человек реально не в агентстве → экран вступления;
  //   • обрыв/5xx/иное → НЕ трогаем агентство: тихо повторяем несколько раз,
  //                      потом показываем экран «нет связи, повторить».
  // Выйти из рабочей оболочки агентства в личное пространство (хаб). Токен
  // оставляем как есть — хаб работает с любым валидным пропуском (/auth/memberships).
  function exitToPersonal() {
    setPhase("personal");
  }

  // Нативный вход (вне Telegram): берём токен у Google/Apple и меняем его на наш
  // пропуск через backend. Сам SDK-шаг (getProviderToken) подключается в Фазе 3;
  // до этого кнопки показывают подсказку.
  // Возвращает текст ошибки (для показа НА экране входа) либо null при успехе.
  async function nativeSignIn(provider: "google" | "apple"): Promise<string | null> {
    try {
      const tok = await getProviderToken(provider);
      if (!tok) return "getProviderToken=null (isNativePlatform ложно?)";
      const path = provider === "google" ? "/api/v1/auth/google" : "/api/v1/auth/apple";
      const body =
        provider === "google"
          ? { id_token: tok.idToken }
          : { identity_token: tok.idToken, first_name: tok.firstName, last_name: tok.lastName };
      const r = await api<AuthResponse>(path, { method: "POST", body });
      if (r.ok && r.data) {
        await applyAuth(r.data);
        return null;
      }
      if (r.status === 0) return "сеть: " + getLastFetchError();
      return "сервер: HTTP " + r.status + " " + (errText(r.data, r.status) || "");
    } catch (e: any) {
      return "исключение: " + (e?.message || e?.code || JSON.stringify(e) || String(e));
    }
  }

  // Вход через Telegram-бота (@realtyloginbot): берём одноразовый код, открываем
  // бота, опрашиваем подтверждение. На confirmed — та же applyAuth, что у Google
  // (внутри неё сессия сохраняется на нативной платформе).
  async function telegramSignIn(): Promise<string | null> {
    try {
      const start = await api<{ code: string; deep_link: string; expires_in: number }>(
        "/api/v1/auth/telegram/start",
        { method: "POST", body: {} }
      );
      if (!start.ok || !start.data) {
        if (start.status === 0) return "сеть: " + getLastFetchError();
        return "сервер: HTTP " + start.status + " " + (errText(start.data, start.status) || "");
      }
      const { code, deep_link } = start.data;
      // "_system" → Capacitor откроет ссылку во внешнем приложении Telegram.
      window.open(deep_link, "_system");

      const deadline = Date.now() + 150000; // ~2.5 мин (TTL кода 5 мин)
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 2000));
        const p = await api<{ status: string; auth?: AuthResponse }>(
          "/api/v1/auth/telegram/poll",
          { method: "POST", body: { code } }
        );
        if (p.ok && p.data) {
          if (p.data.status === "confirmed" && p.data.auth) {
            await applyAuth(p.data.auth);
            return null;
          }
          if (p.data.status === "expired") return "Время вышло, попробуйте войти заново.";
        }
      }
      return "Время вышло, попробуйте войти заново.";
    } catch (e: any) {
      return "исключение: " + (e?.message || String(e));
    }
  }

  const bootstrapping = useRef(false);
  async function bootstrapAuth(): Promise<void> {
    // Защита от параллельных запусков (авто-повтор с экрана «нет связи» не должен
    // накладываться на уже идущую попытку).
    if (bootstrapping.current) return;
    bootstrapping.current = true;
    try {
      const initData = getInitData();
      if (!initData) {
        // Нативное приложение (вне Telegram): восстанавливаем сессию по
        // сохранённому refresh-пропуску; если его нет/недействителен — экран
        // входа Google/Apple. Экран «Откройте в Telegram» тут больше не нужен.
        const sess = await loadSession();
        if (sess?.refresh) {
          const r = await api<AuthResponse>("/api/v1/auth/refresh", {
            method: "POST",
            body: { refresh_token: sess.refresh },
          });
          if (r.ok && r.data) {
            await applyAuth(r.data);
            return;
          }
          // refresh не принят (истёк/отозван) — чистим и просим войти заново.
          if (r.status === 401 || r.status === 403) await clearSession();
        }
        setPhase("login");
        return;
      }
      for (let attempt = 0; attempt < 5; attempt++) {
        const r = await api<AuthResponse>("/api/v1/auth/telegram", { method: "POST", body: { init_data: initData } });
        if (r.ok && r.data) {
          await applyAuth(r.data);
          return;
        }
        if (r.status === 403) {
          setPhase("join");
          return;
        }
        // Временная неудача (обрыв сети / таймаут туннеля / сервер занят):
        // повторяем с нарастающей паузой, НЕ выкидывая пользователя на создание
        // агентства.
        if (attempt < 4) {
          setPhase("loading");
          await new Promise((res) => setTimeout(res, 800 * 2 ** attempt)); // 0.8→1.6→3.2→6.4 c
        }
      }
      setPhase("reconnect");
    } finally {
      bootstrapping.current = false;
    }
  }

  // Войти в другое своё агентство (acting): получить сессию с ролью в нём.
  async function enterAgency(id: number): Promise<boolean> {
    const r = await api<AuthResponse>(`/api/v1/agencies/${id}/enter`, { method: "POST" });
    if (r.ok && r.data) {
      await applyAuth(r.data);
      return true;
    }
    toast(errText(r.data, r.status) || t("loginFail"), "err");
    return false;
  }

  // Открыть ЕЩЁ ОДНО своё агентство (участник становится владельцем) и войти в него.
  async function openAgency(name: string, phone: string): Promise<boolean> {
    const r = await api<AuthResponse>("/api/v1/agencies/open", { method: "POST", body: { name, phone } });
    if (r.ok && r.data) {
      await applyAuth(r.data);
      return true;
    }
    toast(errText(r.data, r.status) || t("loginFail"), "err");
    return false;
  }

  // Удалить СВОЁ агентство (владелец). Сервер возвращает домашнюю сессию.
  async function deleteAgency(id: number): Promise<boolean> {
    const r = await api<AuthResponse>(`/api/v1/agencies/${id}/mine`, { method: "DELETE" });
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
          const res = await fetch(apiUrl("/api/v1/auth/refresh"), {
            method: "POST",
            headers: { "Content-Type": "application/json", ...extraHeaders() },
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
            if (isNativeApp()) void saveSession(data.access_token, refreshTokenRef.current);
            return data.access_token;
          }
        } catch {
          // упадём в запасной путь ниже
        }
      }
      // Запасной путь: повторный вход по initData (если refresh-пропуска нет
      // или он больше не действует).
      const fresh = getInitData();
      if (!fresh) {
        // Нативное приложение: initData нет — восстановить сессию нечем. Значит
        // она недействительна окончательно: чистим и отправляем на экран входа
        // Google/Apple, а не оставляем на бесконечных 401.
        if (isNativeApp()) {
          clearAuth();
          refreshTokenRef.current = null;
          actingAgencyRef.current = null;
          await clearSession();
          setPhase("login");
        }
        return null;
      }
      try {
        const res = await fetch(apiUrl("/api/v1/auth/telegram"), {
          method: "POST",
          headers: { "Content-Type": "application/json", ...extraHeaders() },
          body: JSON.stringify({ init_data: fresh }),
        });
        if (!res.ok) {
          // Сессия/членство недействительны ОКОНЧАТЕЛЬНО (не временный сбой сети
          // или 5xx): выводим пользователя из «мёртвой» рабочей оболочки на нужный
          // экран, а не оставляем на бесконечных ошибках (CR-4). 403 = аккаунт
          // отключён/исключён → экран вступления; 401 = вход не принят → заново.
          if (res.status === 401 || res.status === 403) {
            clearAuth();
            refreshTokenRef.current = null;
            actingAgencyRef.current = null;
            setPhase(res.status === 403 ? "join" : "open");
          }
          return null;
        }
        const data: AuthResponse = await res.json();
        setAuth(data.access_token, data.user, data.subscription_active ?? null);
        refreshTokenRef.current = data.refresh_token ?? refreshTokenRef.current;
        actingAgencyRef.current = data.user.acting_as_agency_id ?? null;
        return data.access_token;
      } catch {
        return null;
      }
    });

    bootstrapAuth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Если владельца разлогинили (передача прав) — вернуться к экрану входа.
  useEffect(() => {
    if (phase === "ready" && !user) setPhase(isNativeApp() ? "login" : "open");
  }, [user, phase]);

  if (phase === "loading") {
    return (
      <div className="pt-24">
        <Spinner />
      </div>
    );
  }
  if (phase === "open") return <OpenInTelegram />;
  if (phase === "login") return <NativeLoginScreen onSignIn={nativeSignIn} onTelegram={telegramSignIn} />;
  if (phase === "reconnect") return <ReconnectScreen onRetry={() => { setPhase("loading"); bootstrapAuth(); }} />;
  if (phase === "join") return <WelcomeScreen prefill={startParam} onAuth={applyAuth} />;
  if (phase === "personal")
    return (
      <>
        <PersonalApp onEnterAgency={(d) => applyAuth(d, { enterAgency: true })} />
        <Toasts />
      </>
    );
  if (phase === "suspended") {
    return (
      <div className="max-w-[560px] mx-auto px-3.5 pt-5">
        <SuspendedScreen />
      </div>
    );
  }

  const initialRoute: Route = user?.role === "superadmin" ? { name: "myAgencies" } : { name: "home" };
  return (
    <NavProvider initial={initialRoute}>
      <ActingProvider value={{ enterAgency, exitToPlatform, openAgency, deleteAgency, exitToPersonal }}>
        <Shell />
      </ActingProvider>
      <Toasts />
    </NavProvider>
  );
}
