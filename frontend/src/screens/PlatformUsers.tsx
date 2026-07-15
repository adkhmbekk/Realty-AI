// Витрина «юзеры прошки» для владельца платформы (Фаза 5, 2026-07).
//
// Самодостаточный экран: список юзеров → карточка (агентства/роли + ЕГО объекты).
// Клиентскую базу НЕ показываем (приватность — так отдаёт и бэкенд). Встройка в
// Superadmin.tsx / нижние вкладки суперадмина делается ОТДЕЛЬНО (со сборкой на pc1).
//
// ВНИМАНИЕ: строки временно локальны (STR) — перенести в i18n.ts при интеграции.
import React, { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronRight, Trash2, RotateCcw, Snowflake, Play, Search as SearchIcon } from "lucide-react";
import { useApp } from "../store";
import type { Lang } from "../i18n";
import { useNav } from "../nav";
import { api, errText } from "../api";
import { Button, Card, Input, Spinner } from "../components/ui";
import { confirmDialog, haptic } from "../telegram";
import { fmtDate } from "../utils";
import { useRevisit } from "../refresh";

interface PUser {
  id: number;
  telegram_id: number;
  username?: string | null;
  full_name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  phone?: string | null;
  is_active: boolean;
  last_seen_at?: string | null;
  last_active_at?: string | null;
  created_at?: string | null;
  archived_at?: string | null;
  agencies_count: number;
  // Присутствие «прямо сейчас»: online / recent / offline (с бэка).
  presence?: string;
  // Вовлечённость «в целом»: active / quiet / asleep / never (с бэка).
  engagement?: string;
}
type Tier = "active" | "quiet" | "asleep" | "never";
interface PUserStats {
  active: number;
  quiet: number;
  asleep: number;
  never: number;
}
interface PUserList {
  items: PUser[];
  total: number;
  limit: number;
  offset: number;
  stats?: PUserStats | null;
}
interface PUserAgency {
  agency_id: number;
  agency_name: string;
  role: string;
  is_owner: boolean;
  is_frozen?: boolean;
  // Присутствие юзера именно в этом агентстве.
  presence?: string;
  last_active_at?: string | null;
}
interface PUserDetail {
  user: PUser;
  agencies: PUserAgency[];
}

const STR: Record<string, Record<string, string>> = {
  ru: {
    users: "Юзеры",
    search: "Поиск по имени / номеру",
    empty: "Юзеры не найдены.",
    agencies: "Агентства",
    objects: "Объекты",
    noObjects: "Объектов пока нет.",
    role_admin: "главный админ",
    role_agent: "агент",
    inAgencies: "агентств",
    back: "Назад",
    activity: "Активность",
    online: "В сети",
    recentSeen: "был(а) только что",
    neverSeen: "ни разу не заходил(а)",
    lastSeen: "Был(а)",
    memberSince: "В приложении с",
    tier_active: "Активные",
    tier_quiet: "Притихли",
    tier_asleep: "Спят",
    tier_never: "Не заходят",
    range_active: "до 3 дн",
    range_quiet: "3–10 дн",
    range_asleep: "10–30 дн",
    range_never: "30 дн+",
    noAgencies: "Пока не состоит в агентствах.",
    tabActive: "Активные", tabArchived: "Архив",
    delete: "Удалить", deleteForever: "Удалить навсегда", restore: "Вернуть",
    confirmDelete: "Удалить пользователя? Он попадёт в архив, а при следующем входе начнёт всё заново.",
    freezeTitle: "Что делать с его агентствами?",
    freezeYes: "Заморозить (агенты потеряют доступ)",
    freezeNo: "Оставить работать",
    confirmPurge: "Удалить НАВСЕГДА? Юзер и все агентства, где он владелец, со всеми объектами будут стёрты безвозвратно.",
    pickTargetTitle: "Кому передать данные",
    pickTargetSub: "Выберите активного пользователя — ему перейдут агентства, где удалённый был владельцем.",
    confirmRestoreTo: "Передать агентства пользователю «{name}»?",
    archivedOk: "В архиве.", restoredOk: "Восстановлено.", purgedOk: "Удалено навсегда.",
    ownerBadge: "владелец", frozenBadge: "заморожено",
    archivedEmpty: "Архив пуст.",
    archivedNote: "Пользователь в архиве. Данные хранятся, пока их не вернуть или не удалить навсегда.",
  },
  uz: {
    users: "Foydalanuvchilar",
    search: "Ism / raqam boʻyicha qidirish",
    empty: "Foydalanuvchilar topilmadi.",
    agencies: "Agentliklar",
    objects: "Obyektlar",
    noObjects: "Hozircha obyekt yoʻq.",
    role_admin: "bosh admin",
    role_agent: "agent",
    inAgencies: "ta agentlik",
    back: "Orqaga",
    activity: "Faollik",
    online: "Onlayn",
    recentSeen: "hozirgina onlayn edi",
    neverSeen: "hech qachon kirmagan",
    lastSeen: "Oxirgi faollik",
    memberSince: "Ilovada",
    tier_active: "Faol",
    tier_quiet: "Jim",
    tier_asleep: "Uxlayapti",
    tier_never: "Kirmaydi",
    range_active: "3 kungacha",
    range_quiet: "3–10 kun",
    range_asleep: "10–30 kun",
    range_never: "30 kun+",
    noAgencies: "Hozircha agentlikda emas.",
    tabActive: "Faol", tabArchived: "Arxiv",
    delete: "Oʻchirish", deleteForever: "Butunlay oʻchirish", restore: "Qaytarish",
    confirmDelete: "Foydalanuvchini oʻchirasizmi? U arxivga tushadi, keyingi kirishda hammasini boshidan boshlaydi.",
    freezeTitle: "Uning agentliklari bilan nima qilamiz?",
    freezeYes: "Muzlatish (agentlar kirolmaydi)",
    freezeNo: "Ishlashda qoldirish",
    confirmPurge: "BUTUNLAY oʻchirilsinmi? Foydalanuvchi va u egasi boʻlgan barcha agentliklar obyektlari bilan qaytarib boʻlmas tarzda oʻchiriladi.",
    pickTargetTitle: "Maʼlumotlar kimga oʻtsin",
    pickTargetSub: "Faol foydalanuvchini tanlang — unga oʻchirilgan egasining agentliklari oʻtadi.",
    confirmRestoreTo: "Agentliklar «{name}» foydalanuvchisiga oʻtkazilsinmi?",
    archivedOk: "Arxivda.", restoredOk: "Tiklandi.", purgedOk: "Butunlay oʻchirildi.",
    ownerBadge: "egasi", frozenBadge: "muzlatilgan",
    archivedEmpty: "Arxiv boʻsh.",
    archivedNote: "Foydalanuvchi arxivda. Maʼlumotlar qaytarilmaguncha yoki butunlay oʻchirilmaguncha saqlanadi.",
  },
  en: {
    users: "Users",
    search: "Search by name / phone",
    empty: "No users found.",
    agencies: "Agencies",
    objects: "Objects",
    noObjects: "No objects yet.",
    role_admin: "main admin",
    role_agent: "agent",
    inAgencies: "agencies",
    back: "Back",
    activity: "Activity",
    online: "Online",
    recentSeen: "was just online",
    neverSeen: "never signed in",
    lastSeen: "Last seen",
    memberSince: "Member since",
    tier_active: "Active",
    tier_quiet: "Quiet",
    tier_asleep: "Asleep",
    tier_never: "Inactive",
    range_active: "<3d",
    range_quiet: "3–10d",
    range_asleep: "10–30d",
    range_never: "30d+",
    noAgencies: "Not in any agency yet.",
    tabActive: "Active", tabArchived: "Archive",
    delete: "Delete", deleteForever: "Delete forever", restore: "Restore",
    confirmDelete: "Delete this user? They go to the archive and start over on their next login.",
    freezeTitle: "What about their agencies?",
    freezeYes: "Freeze (agents lose access)",
    freezeNo: "Keep running",
    confirmPurge: "Delete FOREVER? The user and every agency they own — with all objects — will be erased irreversibly.",
    pickTargetTitle: "Transfer data to",
    pickTargetSub: "Pick an active user — they receive the agencies the deleted user owned.",
    confirmRestoreTo: "Transfer agencies to “{name}”?",
    archivedOk: "Archived.", restoredOk: "Restored.", purgedOk: "Deleted forever.",
    ownerBadge: "owner", frozenBadge: "frozen",
    archivedEmpty: "Archive is empty.",
    archivedNote: "User is archived. Data is kept until restored or deleted forever.",
  },
};

function useStr() {
  const { lang } = useApp();
  return STR[lang] || STR.ru;
}

function displayName(u: PUser): string {
  return (
    [u.first_name, u.last_name].filter(Boolean).join(" ") ||
    u.full_name ||
    (u.username ? "@" + u.username : "#" + u.telegram_id)
  );
}

function roleBadge(role: string, isOwner: boolean, s: Record<string, string>) {
  const admin = isOwner || role === "agency_admin";
  return (
    <span
      className={
        "inline-block px-2.5 py-0.5 rounded-full text-[11px] font-extrabold " +
        (admin
          ? "bg-blue-500/15 text-blue-600 dark:text-blue-400"
          : "bg-slate-500/15 text-slate-600 dark:text-slate-300")
      }
    >
      {admin ? s.role_admin : s.role_agent}
    </span>
  );
}

// Цвет «светофора» тира вовлечённости (совпадает с плашкой-сводкой). Порядок —
// от активных к «не заходят».
const TIERS: Tier[] = ["active", "quiet", "asleep", "never"];
const TIER_DOT: Record<Tier, string> = {
  active: "bg-emerald-500",
  quiet: "bg-amber-500",
  asleep: "bg-violet-500",
  never: "bg-rose-500",
};
const TIER_TEXT: Record<Tier, string> = {
  active: "text-emerald-600 dark:text-emerald-400",
  quiet: "text-amber-600 dark:text-amber-400",
  asleep: "text-violet-600 dark:text-violet-400",
  never: "text-rose-600 dark:text-rose-400",
};

function tierOf(u: PUser): Tier {
  return (TIERS.includes(u.engagement as Tier) ? u.engagement : "never") as Tier;
}

// Цветная точка тира (в углу карточки).
function TierDot({ tier }: { tier: Tier }) {
  return <span className={"w-2.5 h-2.5 rounded-full shrink-0 " + TIER_DOT[tier]} />;
}

// Строка присутствия под именем: «● В сети» / «был(а) только что» / «Был(а): …».
// Для архивных не показывается (вызывающий код это решает).
function PresenceLine({ presence, last_active_at, s, lang }: {
  presence?: string; last_active_at?: string | null; s: Record<string, string>; lang: Lang;
}) {
  if (presence === "online") {
    return (
      <span className="inline-flex items-center gap-1.5 text-[12.5px] font-bold text-emerald-600 dark:text-emerald-400">
        <span className="w-2 h-2 rounded-full bg-emerald-500" /> {s.online}
      </span>
    );
  }
  if (presence === "recent") {
    return <span className="text-[12.5px] text-muted">{s.recentSeen}</span>;
  }
  if (last_active_at) {
    return (
      <span className="text-[12.5px] text-muted">
        {s.lastSeen}: {fmtDate(last_active_at, lang)}
      </span>
    );
  }
  // Ни разу не заходил (нет ни heartbeat, ни логина) — показываем явно, а не пусто.
  return <span className="text-[12.5px] text-muted">{s.neverSeen}</span>;
}

// Нижний лист (портал в body, чтобы всплывал поверх Shell).
function Sheet({ title, sub, onClose, children }: {
  title: string; sub?: string; onClose: () => void; children: React.ReactNode;
}) {
  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-end justify-center"
      style={{ background: "color-mix(in srgb, var(--bg) 68%, transparent)" }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-[560px] bg-card border-t border-line rounded-t-xl3 px-4 pt-3 pb-[calc(18px+env(safe-area-inset-bottom,0px))] animate-fade-up"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="w-10 h-1 rounded-full bg-line mx-auto mb-3.5" />
        <div className="text-[15px] font-extrabold text-center">{title}</div>
        {sub && <div className="text-[12.5px] text-muted text-center mt-1 mb-1">{sub}</div>}
        <div className="mt-3">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

// Выбор активного юзера, которому передать данные удалённого (при «Вернуть»).
function TargetPicker({ s, excludeId, onPick, onClose }: {
  s: Record<string, string>; excludeId: number;
  onPick: (u: PUser) => void; onClose: () => void;
}) {
  const [q, setQ] = useState("");
  const [list, setList] = useState<PUser[] | null>(null);
  const load = useCallback(async (query: string) => {
    setList(null);
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    const r = await api<PUserList>("/api/v1/superadmin/users?" + params.toString());
    setList(r.ok && r.data ? r.data.items.filter((u) => u.id !== excludeId) : []);
  }, [excludeId]);
  useEffect(() => { void load(""); }, [load]);
  return (
    <Sheet title={s.pickTargetTitle} sub={s.pickTargetSub} onClose={onClose}>
      <div className="relative mb-2">
        <SearchIcon size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
        <Input className="pl-9" value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") void load(q); }} placeholder={s.search} />
      </div>
      <div className="space-y-2 max-h-[46vh] overflow-y-auto">
        {list === null ? (
          <div className="py-6 flex justify-center"><Spinner /></div>
        ) : list.length === 0 ? (
          <div className="text-muted text-sm text-center py-6">{s.empty}</div>
        ) : (
          list.map((u) => (
            <button key={u.id} onClick={() => onPick(u)}
              className="w-full flex items-center gap-3 p-3 rounded-xl border border-line bg-card text-left active:scale-[.99] transition">
              <span className="w-9 h-9 rounded-lg bg-primary-soft text-primary flex items-center justify-center font-extrabold shrink-0">
                {(displayName(u)[0] || "?").toUpperCase()}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-bold truncate">{displayName(u)}</span>
                {u.phone && <span className="block text-[12px] text-muted">{u.phone}</span>}
              </span>
              <ChevronRight size={16} className="text-muted shrink-0" />
            </button>
          ))
        )}
      </div>
    </Sheet>
  );
}

export function PlatformUsersScreen() {
  const s = useStr();
  const { lang } = useApp();
  const nav = useNav();
  const [tab, setTab] = useState<"active" | "archived">("active");
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Tier | null>(null);
  const [list, setList] = useState<PUser[] | null>(null);
  const [stats, setStats] = useState<PUserStats | null>(null);

  const load = useCallback(async (query: string, archived: boolean, tier: Tier | null) => {
    setList(null);
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (archived) params.set("archived", "true");
    if (tier && !archived) params.set("engagement", tier);
    const r = await api<PUserList>("/api/v1/superadmin/users?" + params.toString());
    setList(r.ok && r.data ? r.data.items : []);
    setStats(r.ok && r.data ? r.data.stats ?? null : null);
  }, []);

  useEffect(() => {
    // Смена вкладки сбрасывает фильтр по тиру (в архиве он неактуален).
    setFilter(null);
    void load(q, tab === "archived", null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  // Вернулись из карточки юзера после удаления/восстановления/заморозки → тихо
  // обновляем список (мутации в карточке бампают версию данных, см. refresh.ts).
  useRevisit(() => void load(q, tab === "archived", filter));

  // Клик по плашке тира — включить/выключить фильтр (серверный, с пагинацией).
  const toggleFilter = (t: Tier) => {
    haptic();
    const next = filter === t ? null : t;
    setFilter(next);
    void load(q, false, next);
  };

  // ── Список юзеров ───────────────────────────────────────────────────────
  const tabBtn = (id: "active" | "archived", label: string) => (
    <button
      type="button"
      onClick={() => { if (tab !== id) { haptic(); setTab(id); } }}
      className={"flex-1 min-h-[40px] rounded-xl text-[13px] font-bold transition active:scale-95 " +
        (tab === id ? "bg-primary text-white shadow-glow" : "bg-[var(--soft)] text-muted")}
    >
      {label}
    </button>
  );
  return (
    <div className="space-y-3">
      <div className="text-xl font-extrabold tracking-tight mx-0.5">{s.users}</div>
      <div className="flex gap-2">
        {tabBtn("active", s.tabActive)}
        {tabBtn("archived", s.tabArchived)}
      </div>
      <Input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") void load(q, tab === "archived", filter);
        }}
        placeholder={s.search}
      />
      {/* Плашка-сводка по тирам вовлечённости (только активная вкладка). Клик по
          числу — включает/выключает серверный фильтр списка по этому тиру. */}
      {tab === "active" && stats && (
        <div className="grid grid-cols-4 gap-2">
          {TIERS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => toggleFilter(t)}
              className={
                "flex flex-col items-center gap-1 py-2.5 rounded-xl2 border transition active:scale-95 " +
                (filter === t ? "border-primary bg-primary-soft" : "border-line bg-card")
              }
            >
              <span className="flex items-center gap-1.5">
                <span className={"w-2 h-2 rounded-full " + TIER_DOT[t]} />
                <span className={"text-[16px] font-extrabold tabular-nums " + TIER_TEXT[t]}>
                  {stats[t]}
                </span>
              </span>
              <span className="text-[10.5px] font-semibold text-muted leading-tight text-center">
                {s["tier_" + t]}
              </span>
              <span className="text-[9px] text-muted/70 leading-none text-center">
                {s["range_" + t]}
              </span>
            </button>
          ))}
        </div>
      )}
      {list === null ? (
        <Spinner />
      ) : list.length === 0 ? (
        <div className="text-muted text-sm text-center py-8">
          {tab === "archived" ? s.archivedEmpty : s.empty}
        </div>
      ) : (
        <div className="space-y-2">
          {list.map((u) => (
            <button
              key={u.id}
              onClick={() => nav.push({ name: "platformUserDetail", id: u.id })}
              className="w-full flex items-stretch gap-3 p-3.5 rounded-xl2 bg-card border border-line shadow-soft text-left active:scale-[.985] transition"
            >
              <span className="w-11 h-11 rounded-xl bg-primary-soft text-primary flex items-center justify-center font-extrabold shrink-0">
                {(displayName(u)[0] || "?").toUpperCase()}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className="font-extrabold truncate">{displayName(u)}</span>
                </span>
                <span className="block text-muted text-[13px]">
                  {[u.phone, `${u.agencies_count} ${s.inAgencies}`].filter(Boolean).join(" · ")}
                </span>
                {/* Присутствие — только у активных (у архивных статус нерелевантен). */}
                {tab === "active" && (
                  <span className="block mt-0.5">
                    <PresenceLine presence={u.presence} last_active_at={u.last_active_at} s={s} lang={lang} />
                  </span>
                )}
              </span>
              {/* Правый борт: точка тира сверху, шеврон снизу (у архивных — только шеврон). */}
              {tab === "active" ? (
                <span className="flex flex-col items-end justify-between shrink-0 py-0.5">
                  <TierDot tier={tierOf(u)} />
                  <ChevronRight size={16} className="text-muted" />
                </span>
              ) : (
                <span className="ml-auto self-center text-muted text-xl">›</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Карточка юзера (отдельный МАРШРУТ, чтобы «Назад» возвращал в список, а не
// на Главную) ─────────────────────────────────────────────────────────────────
export function PlatformUserDetailScreen({ id }: { id: number }) {
  const s = useStr();
  const { lang, toast } = useApp();
  const nav = useNav();
  const [detail, setDetail] = useState<PUserDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [freezeOpen, setFreezeOpen] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      const r = await api<PUserDetail>(`/api/v1/superadmin/users/${id}`);
      if (alive) setDetail(r.ok && r.data ? r.data : null);
    })();
    return () => { alive = false; };
  }, [id]);

  // Архивация (удаление). freeze — заморозить ли владельческие агентства.
  async function archive(freeze: boolean) {
    if (!detail || busy) return;
    setFreezeOpen(false);
    setBusy(true);
    const r = await api(`/api/v1/superadmin/users/${detail.user.id}/archive`,
      { method: "POST", body: { freeze_agencies: freeze } });
    setBusy(false);
    if (r.ok) { haptic(); toast(s.archivedOk, "ok"); nav.pop(); }
    else toast(errText(r.data, r.status), "err");
  }
  async function onDelete() {
    if (!detail) return;
    if (!(await confirmDialog(s.confirmDelete))) return;
    // Есть владельческие агентства — спрашиваем, заморозить или оставить.
    if (detail.agencies.some((a) => a.is_owner)) setFreezeOpen(true);
    else void archive(false);
  }
  // Восстановление: передать владельческие агентства выбранному юзеру.
  async function restoreTo(target: PUser) {
    if (!detail || busy) return;
    setPickerOpen(false);
    if (!(await confirmDialog(s.confirmRestoreTo.replace("{name}", displayName(target))))) return;
    setBusy(true);
    const r = await api(`/api/v1/superadmin/users/${detail.user.id}/restore`,
      { method: "POST", body: { target_user_id: target.id } });
    setBusy(false);
    if (r.ok) { haptic(); toast(s.restoredOk, "ok"); nav.pop(); }
    else toast(errText(r.data, r.status), "err");
  }
  // Удалить навсегда.
  async function purge() {
    if (!detail || busy) return;
    if (!(await confirmDialog(s.confirmPurge))) return;
    setBusy(true);
    const r = await api(`/api/v1/superadmin/users/${detail.user.id}`, { method: "DELETE" });
    setBusy(false);
    if (r.ok) { haptic(); toast(s.purgedOk, "ok"); nav.pop(); }
    else toast(errText(r.data, r.status), "err");
  }

  if (!detail) return <div className="pt-10"><Spinner /></div>;

  const u = detail.user;
  const online = u.presence === "online";
  const tier = tierOf(u);
  const isArchived = !!u.archived_at;
  return (
    <div className="space-y-3.5">
      <Card>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="text-lg font-extrabold">{displayName(u)}</div>
          {!isArchived && (online ? (
            <span className="inline-flex items-center gap-1 text-[12px] font-bold text-emerald-600 dark:text-emerald-400">
              <span className="w-2 h-2 rounded-full bg-emerald-500" /> {s.online}
            </span>
          ) : (
            <span className={"inline-flex items-center gap-1 text-[12px] font-bold " + TIER_TEXT[tier]}>
              <span className={"w-2 h-2 rounded-full " + TIER_DOT[tier]} /> {s["tier_" + tier]}
            </span>
          ))}
        </div>
        {u.phone && <div className="text-muted text-sm mt-0.5">{u.phone}</div>}
      </Card>

      {isArchived ? (
        <div className="rounded-[14px] px-3.5 py-3 text-[13px] leading-relaxed bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-500/30">
          {s.archivedNote}
        </div>
      ) : (
        <Card>
          <div className="text-[12px] font-bold text-muted mb-1.5">{s.activity}</div>
          {!online && (
            <div className="flex items-center justify-between py-1.5 border-b border-line">
              <span className="text-[13px] text-muted">{s.lastSeen}</span>
              <span className="text-[13px] font-bold">
                {u.presence === "recent"
                  ? s.recentSeen
                  : u.last_active_at
                    ? fmtDate(u.last_active_at, lang)
                    : s.neverSeen}
              </span>
            </div>
          )}
          {u.created_at && (
            <div className="flex items-center justify-between py-1.5 border-b border-line">
              <span className="text-[13px] text-muted">{s.memberSince}</span>
              <span className="text-[13px] font-bold">{fmtDate(u.created_at, lang)}</span>
            </div>
          )}
          <div className="flex items-center justify-between py-1.5">
            <span className="text-[13px] text-muted">{s.agencies}</span>
            <span className="text-[13px] font-bold">{detail.agencies.length}</span>
          </div>
        </Card>
      )}

      {/* Агентства — кликабельны: внутри видно активность и данные агентства. */}
      <div className="text-[14px] font-extrabold mt-1 mx-0.5">{s.agencies}</div>
      {detail.agencies.length === 0 ? (
        <div className="text-muted text-sm text-center py-4">{s.noAgencies}</div>
      ) : (
        <div className="space-y-2">
          {detail.agencies.map((a) => (
            <button
              key={a.agency_id}
              onClick={() => nav.push({ name: "agencyManage", id: a.agency_id })}
              className="w-full flex items-center gap-2 p-3 rounded-xl2 bg-card border border-line shadow-soft text-left active:scale-[.99] transition"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-bold truncate">{a.agency_name}</span>
                  {a.is_frozen && (
                    <span className="shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-sky-500/15 text-sky-600 dark:text-sky-400">
                      <Snowflake size={11} /> {s.frozenBadge}
                    </span>
                  )}
                </div>
                {/* Статус юзера ИМЕННО в этом агентстве. */}
                <div className="mt-0.5">
                  <PresenceLine presence={a.presence} last_active_at={a.last_active_at} s={s} lang={lang} />
                </div>
              </div>
              <span className="shrink-0">{roleBadge(a.role, a.is_owner, s)}</span>
              <ChevronRight size={16} className="text-muted shrink-0" />
            </button>
          ))}
        </div>
      )}

      {/* Действия: активный — «Удалить»; архивный — «Вернуть» + «Удалить навсегда». */}
      <div className="pt-1 space-y-2">
        {isArchived ? (
          <>
            <Button full disabled={busy} onClick={() => setPickerOpen(true)}>
              <RotateCcw size={16} /> {s.restore}
            </Button>
            <Button full variant="danger" disabled={busy} onClick={purge}>
              <Trash2 size={16} /> {s.deleteForever}
            </Button>
          </>
        ) : (
          <Button full variant="danger" disabled={busy} onClick={onDelete}>
            <Trash2 size={16} /> {s.delete}
          </Button>
        )}
      </div>

      {freezeOpen && (
        <Sheet title={s.freezeTitle} onClose={() => setFreezeOpen(false)}>
          <div className="space-y-2.5">
            <Button full variant="danger" disabled={busy} onClick={() => archive(true)}>
              <Snowflake size={16} /> {s.freezeYes}
            </Button>
            <Button full variant="ghost" disabled={busy} onClick={() => archive(false)}>
              <Play size={16} /> {s.freezeNo}
            </Button>
          </div>
        </Sheet>
      )}
      {pickerOpen && (
        <TargetPicker s={s} excludeId={u.id} onPick={restoreTo} onClose={() => setPickerOpen(false)} />
      )}
    </div>
  );
}
