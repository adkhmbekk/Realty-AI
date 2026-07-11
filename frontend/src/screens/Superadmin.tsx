import { confirmDialog, openTelegramLink, haptic } from "../telegram";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { QRCodeSVG } from "qrcode.react";
import { Briefcase, Building2, ChevronRight, Copy, KeyRound, Layers, Link as LinkIcon, Plus, RefreshCw, Send, Trash2, Users, Wallet } from "lucide-react";
import { useApp } from "../store";
import { useNav } from "../nav";
import { useActing } from "../acting";
import { api, errText } from "../api";
import { ApartmentCard } from "./Apartments";
import { Badge, Button, Card, Empty, Field, Hint, Input, ListSkeleton, Row, Spinner } from "../components/ui";
import type { Activation, AgencyActivity, AgencyDraftOut, AgencyOut, AgencyPayment, Apartment, ApartmentList, MlsPoolItem, MlsPoolResponse, PaymentsSummary } from "../types";
import { copyText, fmtAmount, fmtDate } from "../utils";

// Маленький блок «число + подпись» (для Сегодня/Вчера/Позавчера).
function fmtMoneyMap(m?: Record<string, number>): string {
  if (!m) return "";
  return Object.entries(m)
    .map(([c, v]) => new Intl.NumberFormat("ru-RU").format(v) + " " + c)
    .join(" · ");
}

function StatBox({ n, label }: { n: number; label: string }) {
  return (
    <div className="rounded-xl bg-[var(--soft)] py-2 text-center">
      <div className="text-[18px] font-extrabold text-primary leading-none">{n}</div>
      <div className="text-[11px] text-muted mt-1">{label}</div>
    </div>
  );
}

// Полоска доли источника (как добавляют).
function SrcBar({ label, v, total }: { label: string; v: number; total: number }) {
  const pct = total > 0 ? Math.round((v / total) * 100) : 0;
  return (
    <div className="mb-1.5">
      <div className="flex justify-between text-[12px] mb-0.5">
        <span>{label}</span>
        <span className="text-muted">{v} · {pct}%</span>
      </div>
      <div className="h-2 rounded-full bg-[var(--soft)] overflow-hidden">
        <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// Подробный отчёт об активности агентства (внутри карточки агентства).
function AgencyActivityPanel({ id }: { id: number }) {
  const { t, lang } = useApp();
  const [a, setA] = useState<AgencyActivity | null>(null);
  useEffect(() => {
    api<AgencyActivity>(`/api/v1/agencies/${id}/activity`).then((r) => {
      if (r.ok && r.data) setA(r.data);
    });
  }, [id]);
  if (!a) return null;
  const max = Math.max(1, ...a.daily.map((d) => d.added));
  const srcTotal = a.source_manual + a.source_link + a.source_channel;

  return (
    <div className="mt-4">
      <div className="text-[13px] font-extrabold uppercase tracking-wider text-muted mx-0.5 mb-2">
        {t("activityReport")}
      </div>

      {/* Объекты: всего, по статусам, продажа/аренда */}
      <Card>
        <div className="flex items-center justify-between">
          <span className="font-bold">{t("actObjects")}</span>
          <span className="font-extrabold text-primary">{a.objects_total}</span>
        </div>
        <div className="text-[12.5px] text-muted mt-1">
          {t("statusActive")} {a.active} · {t("statusDeposit")} {a.deposit} · {t("statusSold")} {a.sold} · {t("statusRented")} {a.rented}
        </div>
        <div className="text-[12.5px] text-muted">
          {t("dealSale")} {a.sale} · {t("dealRent")} {a.rent}
        </div>
      </Card>

      {/* Добавлено по дням — главное для нового агентства */}
      <Card className="mt-2">
        <div className="grid grid-cols-3 gap-2 mb-2.5">
          <StatBox n={a.added_today} label={t("actAddedDay")} />
          <StatBox n={a.added_yesterday} label={t("actAddedYest")} />
          <StatBox n={a.added_2d} label={t("actAdded2d")} />
        </div>
        <div className="text-[11px] text-muted mb-1">{t("actByDay")}</div>
        <div className="flex items-end gap-1 h-16">
          {a.daily.map((d) => (
            <div
              key={d.date}
              className="flex-1 flex flex-col items-center justify-end h-full"
              title={`${d.date}: ${d.added}`}
            >
              {d.added > 0 && <span className="text-[9px] text-muted leading-none mb-0.5">{d.added}</span>}
              <div
                className="w-full rounded-t bg-primary"
                style={{ height: `${d.added > 0 ? Math.max(10, (d.added / max) * 100) : 3}%` }}
              />
            </div>
          ))}
        </div>
        <div className="text-[11px] text-muted mt-1.5">
          {t("actWeek")}: +{a.added_7d} · {t("actMonth")}: +{a.added_30d}
        </div>
      </Card>

      {/* Как добавляют */}
      {srcTotal > 0 && (
        <Card className="mt-2">
          <div className="font-bold mb-1.5">{t("howAdded")}</div>
          <SrcBar label={t("addManual")} v={a.source_manual} total={srcTotal} />
          <SrcBar label={t("addLink")} v={a.source_link} total={srcTotal} />
          <SrcBar label={t("addBulk")} v={a.added_bulk ?? 0} total={srcTotal} />
          <SrcBar label={t("addAuto")} v={a.added_auto ?? 0} total={srcTotal} />
        </Card>
      )}

      {/* Активность команды */}
      <Card className="mt-2">
        <div className="font-bold mb-1">{t("teamActivity")}</div>
        <Row label={`${t("actLogins")} (7 / 30)`} value={`${a.logins_7d} / ${a.logins_30d}`} />
        <Row label={t("actActiveUsers")} value={`${a.active_users} / ${a.total_users}`} />
        <Row
          label={t("onlineNow")}
          value={
            (a.online_users ?? 0) > 0 ? (
              <span className="inline-flex items-center gap-1.5 font-bold text-emerald-600 dark:text-emerald-400">
                <span className="w-2 h-2 rounded-full bg-emerald-500" /> {a.online_users}
              </span>
            ) : (
              "0"
            )
          }
        />
        <Row label={t("lastActivity")} value={a.last_activity_at ? fmtDate(a.last_activity_at, lang) : "—"} />
      </Card>

      {/* Сделки и комиссия (Волна 7) */}
      {((a.deals_total ?? 0) > 0 || (a.clients_total ?? 0) > 0) && (
        <Card className="mt-2">
          <div className="font-bold mb-1">{t("dealsAnalytics")}</div>
          <Row label={t("cstat_clients")} value={String(a.clients_total ?? 0)} />
          <Row label={t("dealsAll")} value={String(a.deals_total ?? 0)} />
          <Row label={t("cstat_deals_active")} value={String(a.deals_active ?? 0)} />
          <Row label={t("cstat_deals_won")} value={String(a.deals_won ?? 0)} />
          {a.revenue && Object.keys(a.revenue).length > 0 && (
            <Row label={t("commissionTotal")} value={fmtMoneyMap(a.revenue)} />
          )}
        </Card>
      )}

      {/* По сотрудникам */}
      {a.employees.length > 0 && (
        <Card className="mt-2">
          <div className="font-bold mb-1.5">{t("byEmployee")}</div>
          {a.employees.map((e) => (
            <div
              key={e.user_id ?? e.name}
              className="py-2 border-b border-line last:border-0"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium inline-flex items-center gap-1.5 min-w-0">
                  {e.online && <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />}
                  <span className="truncate">{e.name || "—"}</span>
                </span>
                <span className="text-[12px] shrink-0 ml-2 text-right">
                  {e.online ? (
                    <span className="font-bold text-emerald-600 dark:text-emerald-400">{t("online")}</span>
                  ) : (
                    <span className="text-muted">
                      {t("lastSeen")}: {(e.last_seen_at || e.last_login_at) ? fmtDate(e.last_seen_at || e.last_login_at, lang) : t("neverIn")}
                    </span>
                  )}
                </span>
              </div>
              <div className="text-[11.5px] text-muted mt-0.5">
                {t("loginAt")}: {e.last_login_at ? fmtDate(e.last_login_at, lang) : t("neverIn")} · +{e.added} {t("actObjects").toLowerCase()}
                {(e.deals_won ?? 0) > 0
                  ? " · " + t("cstat_deals_won") + ": " + e.deals_won +
                    (e.commission && Object.keys(e.commission).length > 0 ? " · " + fmtMoneyMap(e.commission) : "")
                  : ""}
              </div>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}

function effectiveStatus(a: AgencyOut): string {
  if (a.status === "frozen") return "frozen";
  if (a.subscription_expires_at && new Date(a.subscription_expires_at) < new Date()) return "expired";
  return a.status;
}
function statusBadge(a: AgencyOut, t: (k: string) => string) {
  const eff = effectiveStatus(a);
  const map: Record<string, { c: "green" | "amber" | "red" | "gray"; k: string }> = {
    active: { c: "green", k: "st_active" },
    trial: { c: "green", k: "st_trial" },
    frozen: { c: "amber", k: "st_frozen" },
    expired: { c: "red", k: "st_expired" },
    pending: { c: "amber", k: "st_pending" },
  };
  const m = map[eff] || { c: "gray" as const, k: eff };
  return <Badge color={m.c}>{map[eff] ? t(m.k) : eff}</Badge>;
}

function payActionLabel(action: string, t: (k: string) => string): string {
  const map: Record<string, string> = {
    extend: t("payExtend"),
    set: t("paySet"),
    freeze: t("payFreeze"),
    activate: t("payActivate"),
  };
  return map[action] || action;
}

function fmtTotals(arr: { currency: string; amount: number }[]): string {
  if (!arr.length) return "—";
  return arr.map((c) => `${fmtAmount(c.amount)} ${c.currency}`).join(" · ");
}

// Карточка ссылки активации агентства (создание «по ссылке»).
function ActivationCard({
  activation,
  onReissue,
  onRevoke,
}: {
  activation: Activation;
  onReissue?: () => void;
  onRevoke?: () => void;
}) {
  const { t, lang, toast } = useApp();
  const link = activation.link || "";
  async function copy() {
    const ok = await copyText(link);
    toast(ok ? t("copied") : t("copy"), ok ? "ok" : "info");
  }
  async function doCopyCode() {
    const ok = await copyText(activation.code);
    toast(ok ? t("copied") : t("copy"), ok ? "ok" : "info");
  }
  function share() {
    if (!link) return;
    const url =
      "https://t.me/share/url?url=" +
      encodeURIComponent(link) +
      "&text=" +
      encodeURIComponent(t("activationShareText"));
    openTelegramLink(url);
  }
  return (
    <Card className="mt-3">
      <div className="flex items-center gap-2 mb-1.5">
        <span
          className="w-8 h-8 rounded-[10px] flex items-center justify-center text-white shadow-glow shrink-0"
          style={{ background: "var(--grad)" }}
        >
          <LinkIcon size={16} />
        </span>
        <span className="font-extrabold">{t("activationTitle")}</span>
      </div>
      <Hint>{t("activationHint")}</Hint>
      {link && (
        <>
          {/* QR на белом фоне — чтобы сканировался и в тёмной теме. */}
          <div className="flex justify-center mt-3">
            <div className="bg-white p-3 rounded-2xl shadow-soft">
              <QRCodeSVG value={link} size={168} marginSize={2} />
            </div>
          </div>
          <div className="mt-3 rounded-xl bg-[var(--soft)] border border-line px-3 py-2 text-[12px] break-all select-all">
            {link}
          </div>
        </>
      )}
      {/* Код активации — запасной путь: если приложение попросит код, клиент
          вставляет его (активирует агентство так же, как и переход по ссылке). */}
      <div className="mt-2 flex items-center justify-between gap-2 rounded-xl bg-primary-soft border border-primary px-3 py-2">
        <div className="min-w-0">
          <div className="text-[11px] text-muted">{t("activationCode")}</div>
          <div className="font-extrabold text-primary text-[15px] tracking-wide break-all select-all">
            {activation.code}
          </div>
        </div>
        <Button size="sm" variant="ghost" onClick={doCopyCode}>
          <Copy size={15} /> {t("copyCode")}
        </Button>
      </div>
      <div className="text-[12px] text-muted mt-1.5">
        {t("activationExpires")}: {fmtDate(activation.expires_at, lang)}
      </div>
      <div className="grid grid-cols-2 gap-2 mt-3">
        <Button size="sm" onClick={share}>
          <Send size={15} /> {t("activationShare")}
        </Button>
        <Button size="sm" variant="ghost" onClick={copy}>
          <Copy size={15} /> {t("copyLink")}
        </Button>
        {onReissue && (
          <Button size="sm" variant="ghost" onClick={onReissue}>
            <RefreshCw size={15} /> {t("activationReissue")}
          </Button>
        )}
        {onRevoke && (
          <Button size="sm" variant="danger" onClick={onRevoke}>
            <Trash2 size={15} /> {t("activationRevoke")}
          </Button>
        )}
      </div>
    </Card>
  );
}


// Свод по платежам всех агентств (общий итог + статистика).
function RevenuePanel() {
  const { t } = useApp();
  const [s, setS] = useState<PaymentsSummary | null>(null);
  useEffect(() => {
    api<PaymentsSummary>("/api/v1/agencies/payments/summary").then((r) => {
      if (r.ok && r.data) setS(r.data);
    });
  }, []);
  if (!s) return null;
  return (
    <Card className="mt-3">
      <div className="font-extrabold mb-1">{t("revenue")}</div>
      <Row label={t("revenueAllTime")} value={fmtTotals(s.all_time)} />
      <Row label={t("revenueMonth")} value={fmtTotals(s.this_month)} />
      <Row label={t("paymentsCount")} value={String(s.total_records)} />
    </Card>
  );
}

// История платежей конкретного агентства.
function PaymentHistory({ id, refresh }: { id: number; refresh: number }) {
  const { t, lang, toast } = useApp();
  const [items, setItems] = useState<AgencyPayment[] | null>(null);
  const [bump, setBump] = useState(0);

  async function load() {
    const r = await api<AgencyPayment[]>("/api/v1/agencies/" + id + "/payments");
    setItems(r.ok && Array.isArray(r.data) ? r.data : []);
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, refresh, bump]);

  async function del(p: AgencyPayment) {
    if (!(await confirmDialog(t("delPaymentQ")))) return;
    const r = await api("/api/v1/agencies/" + id + "/payments/" + p.id, { method: "DELETE" });
    if (r.ok) {
      toast(t("saved"), "ok");
      setBump((b) => b + 1);
    } else toast(errText(r.data, r.status), "err");
  }

  if (!items) return null;
  return (
    <div className="mt-4">
      <div className="text-[13px] font-extrabold uppercase tracking-wider text-muted mx-0.5 mb-2">
        {t("paymentHistory")}
      </div>
      {!items.length ? (
        <Empty>{t("noPayments")}</Empty>
      ) : (
        items.map((p) => (
          <Card key={p.id} className="mt-2">
            <div className="flex items-center justify-between gap-2">
              <span className="font-bold">
                {payActionLabel(p.action, t)}
                {p.days ? ` · +${p.days} ${t("daysShort")}` : ""}
              </span>
              <span className="flex items-center gap-2 shrink-0">
                <span className="font-extrabold text-primary">
                  {p.amount != null ? `${fmtAmount(p.amount)} ${p.currency || ""}` : "—"}
                </span>
                <button onClick={() => del(p)} aria-label={t("deleteAction")} className="p-1 text-muted hover:text-[var(--danger)] active:scale-90 transition">
                  <Trash2 size={15} />
                </button>
              </span>
            </div>
            <div className="text-[12px] text-muted">{fmtDate(p.created_at, lang)}</div>
            {p.note && <div className="text-[12px] text-muted">{p.note}</div>}
          </Card>
        ))
      )}
    </div>
  );
}

// Финансы платформы: ТОЛЬКО деньги (свод по доходу/платежам). Агентства сюда
// больше не входят — они теперь внутри своих пользователей (вкладка «Пользователи»
// → юзер → его агентства). Управление/активность агентства открывается оттуда.
export function AgenciesScreen() {
  const { t } = useApp();
  return (
    <div>
      <div className="text-xl font-extrabold tracking-tight mx-0.5 mb-1">{t("financesTab")}</div>
      <p className="text-[13px] text-muted mx-0.5 mb-1">{t("financesSub")}</p>
      <RevenuePanel />
    </div>
  );
}

// ── Личные агентства владельца платформы ────────────────────────────────────
// Здесь владелец создаёт СВОИ агентства (где он сам — главный админ) и «входит»
// в них, получая обычный интерфейс агентства. Создание — через простой prompt,
// чтобы не плодить отдельный экран (нужно только название).
// Личный хаб суперадмина: он тоже юзер, но видит больше. Главная — кнопки:
// Финансы, Мои агентства (→ отдельная страница), Пользователи, Общая база.
// Настройки/Профиль хаба идентичны пользовательским (см. Personal.tsx обёртки).
export function MyAgenciesScreen() {
  const { t, user } = useApp();
  const nav = useNav();
  const hubName = [user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.full_name || "Realty AI";

  const NavRow = ({ icon, chip, label, sub, onClick }: { icon: JSX.Element; chip: string; label: string; sub?: string; onClick: () => void }) => (
    <button
      onClick={() => { haptic(); onClick(); }}
      className="w-full flex items-center gap-3 rounded-xl2 bg-card border border-line shadow-soft p-3.5 active:scale-[.99] transition"
    >
      <span className={"w-10 h-10 rounded-xl flex items-center justify-center shrink-0 " + chip}>{icon}</span>
      <span className="min-w-0 flex-1 text-left">
        <span className="block font-extrabold">{label}</span>
        {sub && <span className="block text-[12px] text-muted">{sub}</span>}
      </span>
      <ChevronRight size={18} className="text-muted shrink-0" />
    </button>
  );

  return (
    <div>
      {/* Шапка хаба */}
      <div className="rounded-xl3 px-5 py-5 text-white overflow-hidden mb-3" style={{ background: "var(--grad-hero)", boxShadow: "0 16px 40px rgba(52,31,163,.30)" }}>
        <div className="text-[13px] opacity-85">Realty <span className="opacity-100 font-extrabold">AI</span> · {t("superadminHubSub")}</div>
        <div className="text-[20px] font-extrabold leading-tight truncate mt-0.5">{hubName}</div>
      </div>

      <div className="space-y-2.5">
        {/* Финансы — первым */}
        <NavRow icon={<Wallet size={18} />} chip="bg-amber-500/15 text-amber-600 dark:text-amber-400" label={t("financesTab")} sub={t("financesSub")} onClick={() => nav.push({ name: "agencies" })} />
        {/* Мои агентства — кнопка → страница со списком */}
        <NavRow icon={<Building2 size={18} />} chip="bg-indigo-500/15 text-indigo-600 dark:text-indigo-400" label={t("myAgenciesTitle")} onClick={() => nav.push({ name: "personalAgencies" })} />
        {/* Пользователи */}
        <NavRow icon={<Users size={18} />} chip="bg-emerald-500/15 text-emerald-600 dark:text-emerald-400" label={t("usersTab")} onClick={() => nav.push({ name: "platformUsers" })} />
        {/* Общая база MLS */}
        <NavRow icon={<Layers size={18} />} chip="bg-sky-500/15 text-sky-600 dark:text-sky-400" label={t("mlsTab")} onClick={() => nav.push({ name: "mlsPool" })} />
      </div>
    </div>
  );
}

// Страница «Мои агентства» суперадмина: список (Realty AI + личные) + кнопка
// «Добавить» справа → нижний лист «Создать агентство / Вступить по коду»
// (то же самое, что у юзеров). Тап по агентству — вход (acting).
export function PersonalAgenciesScreen() {
  const { t, toast } = useApp();
  const nav = useNav();
  const { enterAgency } = useActing();
  const [list, setList] = useState<AgencyOut[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [choice, setChoice] = useState(false);
  const [busy, setBusy] = useState(false);

  async function load() {
    const r = await api<AgencyOut[]>("/api/v1/agencies/mine");
    if (r.ok && Array.isArray(r.data)) {
      setList(r.data);
      setErr(null);
    } else setErr(`${t("notFound")} (${r.status})`);
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function create() {
    setChoice(false);
    const v = window.prompt(t("personalAgencyNamePrompt"), "");
    if (v === null || !v.trim()) return;
    setBusy(true);
    const r = await api("/api/v1/agencies/mine", { method: "POST", body: { name: v.trim() } });
    setBusy(false);
    if (r.ok) {
      toast(t("agencyCreated"), "ok");
      load();
    } else toast(errText(r.data, r.status), "err");
  }
  async function join() {
    setChoice(false);
    const code = window.prompt(t("codePrompt"), "")?.trim();
    if (!code) return;
    const r = await api("/api/v1/invites/redeem", { method: "POST", body: { code } });
    if (r.ok) {
      toast(t("joined"), "ok");
      load();
    } else toast(errText(r.data, r.status), "err");
  }
  async function enter(id: number) {
    const ok = await enterAgency(id);
    if (ok) nav.resetTo({ name: "home" });
  }

  return (
    <div>
      <div className="flex items-center justify-between mx-0.5 mb-2.5">
        <span className="text-[14px] font-extrabold">{t("myAgenciesTitle")}</span>
        <Button variant="soft" size="sm" disabled={busy} onClick={() => { haptic(); setChoice(true); }}>
          <Plus size={15} /> {t("createAgencyShort")}
        </Button>
      </div>
      {err ? (
        <Empty>{err}</Empty>
      ) : !list ? (
        <ListSkeleton />
      ) : !list.length ? (
        <Empty icon={<Briefcase size={24} />}>{t("noPersonalAgencies")}</Empty>
      ) : (
        <div className="space-y-2.5">
          {list.map((a) => (
            <button
              key={a.id}
              onClick={() => enter(a.id)}
              className="w-full flex items-center gap-3 p-3.5 rounded-xl2 bg-card border border-line shadow-soft text-left active:scale-[.985] transition"
            >
              <span className="w-11 h-11 rounded-xl bg-primary-soft text-primary flex items-center justify-center shrink-0"><Building2 size={18} /></span>
              <span className="min-w-0 flex-1">
                <span className="block font-extrabold truncate">{a.project_name || a.name}</span>
                {a.is_shared && (
                  <span className="inline-block mt-1 px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-primary-soft text-primary">{t("sharedAgencyBadge")}</span>
                )}
              </span>
              <ChevronRight size={18} className="text-muted shrink-0" />
            </button>
          ))}
        </div>
      )}

      {/* Нижний лист: создать / вступить (портал в body, чтобы всплывал поверх). */}
      {choice && createPortal(
        <div
          className="fixed inset-0 z-[100] flex items-end justify-center"
          style={{ background: "color-mix(in srgb, var(--bg) 68%, transparent)" }}
          onClick={() => setChoice(false)}
        >
          <div
            className="w-full max-w-[560px] bg-card border-t border-line rounded-t-xl3 px-4 pt-3 pb-[calc(18px+env(safe-area-inset-bottom,0px))] animate-fade-up"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="w-10 h-1 rounded-full bg-line mx-auto mb-3.5" />
            <div className="text-[15px] font-extrabold text-center mb-3">{t("addAgencyTitle")}</div>
            <div className="space-y-2.5">
              <Button full onClick={create}><Plus size={16} /> {t("createAgency")}</Button>
              <Button variant="ghost" full onClick={join}><KeyRound size={16} /> {t("joinByCode")}</Button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}

export function AgencyCreateScreen() {
  const { t, toast } = useApp();
  const nav = useNav();
  const [name, setName] = useState("");
  const [days, setDays] = useState("30");
  const [phone, setPhone] = useState("");
  const [saving, setSaving] = useState(false);
  // После создания — показываем ссылку активации (Telegram ID искать не нужно).
  const [result, setResult] = useState<AgencyDraftOut | null>(null);

  async function create() {
    if (!name.trim()) {
      toast(t("emptyName"), "warn");
      return;
    }
    const parsedDays = parseInt(days, 10);
    if (Number.isNaN(parsedDays) || parsedDays <= 0) {
      toast(t("badDate"), "warn");
      return;
    }
    setSaving(true);
    const body: Record<string, unknown> = {
      name: name.trim(),
      subscription_days: parsedDays,
    };
    if (phone.trim()) body.client_phone = phone.trim();
    const r = await api<AgencyDraftOut>("/api/v1/agencies/draft", { method: "POST", body });
    setSaving(false);
    if (r.ok && r.data) {
      setResult(r.data);
      toast(t("agencyDraftCreated"), "ok");
    } else toast(errText(r.data, r.status), "err");
  }

  if (result) {
    return (
      <div>
        <Card>
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className="text-[16px] font-extrabold">{result.agency.name}</span>
            {statusBadge(result.agency, t)}
          </div>
          <Row label="ID" value={result.agency.id} />
        </Card>
        <ActivationCard activation={result.activation} />
        <Button
          full
          className="mt-4"
          onClick={() => {
            nav.pop();
            nav.push({ name: "agencyManage", id: result.agency.id });
          }}
        >
          {t("toAgency")}
        </Button>
      </div>
    );
  }

  return (
    <Card>
      <Field label={t("agencyName")}>
        <Input value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label={t("subDays")}>
        <Input inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value)} />
      </Field>
      <Field label={t("agencyPhoneOpt")}>
        <Input inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
      </Field>
      <Hint>{t("agencyPhoneHint")}</Hint>
      <Button full className="mt-4" disabled={saving} onClick={create}>
        {t("createAgency")}
      </Button>
    </Card>
  );
}

export function AgencyManageScreen({ id }: { id: number }) {
  const { t, lang, toast } = useApp();
  const nav = useNav();
  const [a, setA] = useState<AgencyOut | null>(null);
  const [activation, setActivation] = useState<Activation | null>(null);
  const [loading, setLoading] = useState(true);
  const [payKey, setPayKey] = useState(0);

  async function load() {
    setLoading(true);
    const r = await api<AgencyOut[]>("/api/v1/agencies");
    setLoading(false);
    if (r.ok && Array.isArray(r.data)) {
      const found = r.data.find((x) => x.id === id) || null;
      setA(found);
      // У черновика (ожидает активации) подгружаем ссылку активации.
      if (found && found.status === "pending") {
        const av = await api<Activation>("/api/v1/agencies/" + id + "/activation");
        setActivation(av.ok && av.data ? av.data : null);
      } else {
        setActivation(null);
      }
    }
  }

  async function reissueActivation() {
    const r = await api<Activation>("/api/v1/agencies/" + id + "/activation", { method: "POST" });
    if (r.ok && r.data) {
      setActivation(r.data);
      toast(t("activationReissued"), "ok");
    } else toast(errText(r.data, r.status), "err");
  }
  async function revokeActivation() {
    if (!(await confirmDialog(t("activationRevokeQ")))) return;
    const r = await api("/api/v1/agencies/" + id + "/activation", { method: "DELETE" });
    if (r.ok) {
      setActivation(null);
      toast(t("activationRevoked"), "ok");
    } else toast(errText(r.data, r.status), "err");
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function sub(action: string, days?: number, expiresAt?: string, amount?: number, currency?: string) {
    const body: Record<string, unknown> = { action };
    if (days != null) body.days = days;
    if (expiresAt) body.expires_at = expiresAt;
    if (amount != null) body.amount = amount;
    if (currency) body.currency = currency;
    const r = await api("/api/v1/agencies/" + id + "/subscription", { method: "POST", body });
    if (r.ok) {
      toast(t("subUpdated"), "ok");
      setPayKey((k) => k + 1);
      load();
    } else toast(errText(r.data, r.status), "err");
  }

  if (loading) return <Spinner />;
  if (!a) return <Empty>{t("notFound")}</Empty>;
  const frozen = a.status === "frozen";
  const adminTxt = a.admin_name
    ? a.admin_name + (a.admin_telegram_id ? ` (ID ${a.admin_telegram_id})` : "")
    : t("notAssigned");

  function extend() {
    const v = window.prompt(t("extendPrompt"), "30");
    if (v === null) return;
    const d = parseInt(v.trim(), 10);
    if (Number.isNaN(d) || d <= 0) {
      toast(t("badDate"), "warn");
      return;
    }
    const av = window.prompt(t("amountPrompt"), "0");
    if (av === null) return;
    const amount = parseFloat((av || "").trim().replace(",", "."));
    if (Number.isNaN(amount) || amount < 0) {
      toast(t("badAmount"), "warn");
      return;
    }
    let currency = "";
    if (amount > 0) {
      const cv = window.prompt(t("currencyPrompt"), "USD");
      if (cv === null) return;
      currency = (cv || "").trim().toUpperCase();
      if (!currency) {
        toast(t("badCurrency"), "warn");
        return;
      }
    }
    sub("extend", d, undefined, amount, currency || undefined);
  }
  function changeDate() {
    const v = window.prompt(t("setDatePrompt"), "");
    if (v === null) return;
    const s = v.trim();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) {
      toast(t("badDate"), "warn");
      return;
    }
    sub("set", undefined, s + "T23:59:59Z");
  }
  async function rename() {
    const v = window.prompt(t("newName"), a!.name);
    if (v === null) return;
    if (!v.trim()) {
      toast(t("emptyName"), "warn");
      return;
    }
    const r = await api("/api/v1/agencies/" + id, { method: "PATCH", body: { name: v.trim() } });
    if (r.ok) {
      toast(t("renamed"), "ok");
      load();
    } else toast(errText(r.data, r.status), "err");
  }
  async function changePhone() {
    const v = window.prompt(t("setPhonePrompt"), a!.client_phone || "");
    if (v === null) return;
    // Пустая строка очищает номер (бэкенд приводит к NULL).
    const r = await api("/api/v1/agencies/" + id, { method: "PATCH", body: { client_phone: v.trim() } });
    if (r.ok) {
      toast(t("saved"), "ok");
      load();
    } else toast(errText(r.data, r.status), "err");
  }
  async function changeAdmin() {
    const idStr = window.prompt(t("promptAdminId"), "");
    if (idStr === null) return;
    const tgId = parseInt(idStr.trim(), 10);
    if (Number.isNaN(tgId)) {
      toast(t("badId"), "warn");
      return;
    }
    const username = window.prompt(t("promptAdminUser"), "");
    if (username === null) return;
    const body: Record<string, unknown> = { admin_telegram_id: tgId };
    const u = username.trim();
    if (u) body.admin_username = u;
    const r = await api("/api/v1/agencies/" + id + "/admin", { method: "POST", body });
    if (r.ok) {
      toast(t("adminAssigned"), "ok");
      load();
    } else toast(errText(r.data, r.status), "err");
  }
  async function del() {
    if (!(await confirmDialog(t("delAgQ1")))) return;
    if (!(await confirmDialog(t("delAgQ2")))) return;
    const r = await api("/api/v1/agencies/" + id, { method: "DELETE" });
    if (r.ok) {
      toast(t("agDeleted"), "ok");
      nav.pop();
    } else toast(errText(r.data, r.status), "err");
  }

  const pending = a.status === "pending";
  return (
    <div>
      <Card>
        <div className="flex items-center justify-between gap-2 mb-1">
          <span className="text-[16px] font-extrabold">{a.name}</span>
          {statusBadge(a, t)}
        </div>
        {a.project_name && <Row label={t("projectName")} value={a.project_name} />}
        <Row label="ID" value={a.id} />
        {!pending && <Row label={t("activatedAt")} value={fmtDate(a.activated_at || a.created_at, lang)} />}
        {!pending && <Row label={t("subUntil")} value={fmtDate(a.subscription_expires_at, lang)} />}
        {!pending && <Row label={t("admin")} value={adminTxt} />}
        <Row label={t("agencyPhone")} value={a.client_phone || t("notSet")} />
      </Card>

      {pending ? (
        /* Черновик: главное — ссылка активации; полное управление появится после. */
        <>
          {activation ? (
            <ActivationCard activation={activation} onReissue={reissueActivation} onRevoke={revokeActivation} />
          ) : (
            <Card className="mt-3">
              <Hint>{t("activationNone")}</Hint>
              <Button full className="mt-2" onClick={reissueActivation}>
                <LinkIcon size={16} /> {t("activationCreate")}
              </Button>
            </Card>
          )}
          <div className="mt-3 grid grid-cols-2 gap-2">
            <Button full size="sm" variant="ghost" onClick={rename}>
              {t("rename")}
            </Button>
            <Button full size="sm" variant="ghost" onClick={changePhone}>
              {t("changePhone")}
            </Button>
            <Button full size="sm" variant="danger" onClick={del}>
              {t("deleteAgency")}
            </Button>
          </div>
        </>
      ) : (
        <>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <Button full size="sm" variant="ghost" onClick={extend}>
              {t("extendBtn")}
            </Button>
            <Button full size="sm" variant="ghost" onClick={changeDate}>
              {t("changeDateBtn")}
            </Button>
            <Button full size="sm" variant="ghost" onClick={rename}>
              {t("rename")}
            </Button>
            <Button full size="sm" variant="ghost" onClick={changeAdmin}>
              {t("changeAdmin")}
            </Button>
            <Button full size="sm" variant="ghost" onClick={changePhone}>
              {t("changePhone")}
            </Button>
            <Button full size="sm" variant={frozen ? "ghost" : "danger"} onClick={() => sub(frozen ? "activate" : "freeze")}>
              {frozen ? t("activate") : t("freeze")}
            </Button>
            <Button full size="sm" variant="danger" onClick={del}>
              {t("deleteAgency")}
            </Button>
          </div>
          <Button full variant="ghost" className="mt-3" onClick={() => nav.push({ name: "agencyObjects", id })}>
            <Building2 size={16} /> {t("agencyObjectsBtn")}
          </Button>
          <AgencyActivityPanel id={id} />
          <PaymentHistory id={id} refresh={payKey} />
        </>
      )}
    </div>
  );
}

// ── Объекты агентства (просмотр владельцем платформы) ────────────────────────
// Та же карточка, что и в своей базе (ApartmentCard: фото слева, красиво), но
// БЕЗ номера собственника (бэкенд его обнулил). Тап → полная read-only карточка.
export function AgencyObjectsScreen({ id }: { id: number }) {
  const { t } = useApp();
  const nav = useNav();
  const [items, setItems] = useState<Apartment[] | null>(null);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const PAGE = 30;

  async function load(reset: boolean) {
    setLoading(true);
    const offset = reset ? 0 : items?.length ?? 0;
    const p = new URLSearchParams();
    p.set("limit", String(PAGE));
    p.set("offset", String(offset));
    if (q.trim()) p.set("q", q.trim());
    const r = await api<ApartmentList>("/api/v1/agencies/" + id + "/objects?" + p.toString());
    setLoading(false);
    if (r.ok && r.data) {
      const data = r.data;
      setTotal(data.total);
      setItems(reset ? data.items : (prev) => [...(prev ?? []), ...data.items]);
    } else if (reset) {
      setItems([]);
    }
  }
  useEffect(() => {
    load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <div className="flex gap-2 mb-1">
        <Input
          placeholder={t("clientSearch")}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") load(true);
          }}
        />
        <Button onClick={() => load(true)}>{t("filterBtn")}</Button>
      </div>
      <div className="text-[13px] text-muted mb-1">
        {t("actObjects")}: <b>{total}</b>
      </div>
      {!items ? (
        <ListSkeleton />
      ) : !items.length ? (
        <Empty icon={<Building2 size={24} />}>{t("noObjectsYet")}</Empty>
      ) : (
        <>
          {items.map((o) => (
            <ApartmentCard key={o.id} o={o} onOpen={() => nav.push({ name: "agencyObjectDetail", obj: o, agencyId: id })} />
          ))}
          {items.length < total && (
            <Button full variant="ghost" className="mt-3" disabled={loading} onClick={() => load(false)}>
              {t("loadMore")}
            </Button>
          )}
        </>
      )}
    </div>
  );
}

// ── Витрина общей базы (MLS) для владельца платформы ────────────────────────
// Объекты общей базы (MLS) для суперадмина рисуются общей ApartmentCard (фото
// слева, как в своей базе) и ОТКРЫВАЮТСЯ в read-only карточку объекта (без
// номера собственника). Над карточкой — бейдж агентства-владельца. См. MlsPoolScreen.

export function MlsPoolScreen() {
  const { t } = useApp();
  const nav = useNav();
  const [agencies, setAgencies] = useState<AgencyOut[]>([]);
  const [agencyId, setAgencyId] = useState<string>("");
  const [dealType, setDealType] = useState<"" | "sale" | "rent">("");
  // Статус объекта: "" = любой (по умолчанию показываем ВСЕ, а не только active —
  // раньше эндпоинт молча фильтровал active, и «фильтр не работал»: проданные/
  // сданные не показывались, а статус выбрать было негде).
  const [status, setStatus] = useState<string>("");
  const [q, setQ] = useState("");
  const [items, setItems] = useState<MlsPoolItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const PAGE = 30;

  async function load(reset: boolean) {
    setLoading(true);
    const offset = reset ? 0 : items.length;
    const p = new URLSearchParams();
    p.set("limit", String(PAGE));
    p.set("offset", String(offset));
    if (agencyId) p.set("agency_id", agencyId);
    if (dealType) p.set("deal_type", dealType);
    // Пустой статус шлём явно: сервер по умолчанию берёт "active", а нам нужно
    // «любой». Пустая строка на бэке = без фильтра по статусу.
    p.set("status", status);
    if (q.trim()) p.set("q", q.trim());
    const r = await api<MlsPoolResponse>("/api/v1/mls/pool?" + p.toString());
    setLoading(false);
    if (r.ok && r.data) {
      const data = r.data;
      setTotal(data.total);
      setItems(reset ? data.items : (prev) => [...prev, ...data.items]);
      setErr(null);
    } else {
      setErr(`${t("notFound")} (${r.status})`);
    }
  }

  useEffect(() => {
    api<AgencyOut[]>("/api/v1/agencies").then((r) => {
      if (r.ok && Array.isArray(r.data)) setAgencies(r.data);
    });
  }, []);

  // Смена агентства/типа сделки/статуса — перезагрузка с начала (поиск по тексту — по кнопке).
  useEffect(() => {
    load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agencyId, dealType, status]);

  const pill = (active: boolean) =>
    "min-h-[44px] px-3.5 py-2 rounded-full text-[13px] font-bold transition active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] " +
    (active ? "bg-primary text-white shadow-glow" : "bg-[var(--soft)] text-muted");

  return (
    <div>
      <Hint>{t("mlsPoolHint")}</Hint>

      <div className="flex gap-2 mt-3">
        <button type="button" className={pill(dealType === "")} onClick={() => setDealType("")}>
          {t("dealAll")}
        </button>
        <button type="button" className={pill(dealType === "sale")} onClick={() => setDealType("sale")}>
          {t("dealSale")}
        </button>
        <button type="button" className={pill(dealType === "rent")} onClick={() => setDealType("rent")}>
          {t("dealRent")}
        </button>
      </div>

      {/* Статус — независимо от типа сделки; «Все» доступно всегда. */}
      <div className="flex flex-wrap gap-2 mt-2">
        <button type="button" className={pill(status === "")} onClick={() => setStatus("")}>
          {t("dealAll")}
        </button>
        <button type="button" className={pill(status === "active")} onClick={() => setStatus("active")}>
          {t("statusActive")}
        </button>
        <button type="button" className={pill(status === "deposit")} onClick={() => setStatus("deposit")}>
          {t("statusDeposit")}
        </button>
        <button type="button" className={pill(status === "sold")} onClick={() => setStatus("sold")}>
          {t("statusSold")}
        </button>
        <button type="button" className={pill(status === "rented")} onClick={() => setStatus("rented")}>
          {t("statusRented")}
        </button>
      </div>

      <select
        value={agencyId}
        onChange={(e) => setAgencyId(e.target.value)}
        aria-label={t("mlsAllAgencies")}
        className="w-full mt-2 min-h-[44px] rounded-xl border border-line bg-card px-3 py-2.5 text-[14px]"
      >
        <option value="">{t("mlsAllAgencies")}</option>
        {agencies.map((a) => (
          <option key={a.id} value={String(a.id)}>
            {a.name}
          </option>
        ))}
      </select>

      <div className="flex gap-2 mt-2">
        <Input
          placeholder={t("mlsSearchPlaceholder")}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") load(true);
          }}
        />
        <Button onClick={() => load(true)}>{t("filterBtn")}</Button>
      </div>

      <div className="text-[13px] text-muted mt-3">
        {t("mlsTotal")}: <b>{total}</b>
      </div>

      <div className="mt-1">
        {err ? (
          <Empty>{err}</Empty>
        ) : loading && items.length === 0 ? (
          <ListSkeleton />
        ) : !items.length ? (
          <Empty icon={<Building2 size={24} />}>{t("mlsEmpty")}</Empty>
        ) : (
          <>
            {items.map((it) => (
              <ApartmentCard
                key={it.apartment.id}
                o={it.apartment}
                agencyName={it.agency_name || `ID ${it.agency_id}`}
                onOpen={() => nav.push({ name: "agencyObjectDetail", obj: it.apartment, agencyId: it.agency_id })}
              />
            ))}
            {items.length < total && (
              <Button full variant="ghost" className="mt-3" disabled={loading} onClick={() => load(false)}>
                {t("loadMore")}
              </Button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
