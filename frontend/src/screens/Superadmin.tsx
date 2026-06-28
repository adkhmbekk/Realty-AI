import { confirmDialog, openTelegramLink } from "../telegram";
import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Briefcase, Building2, Copy, Link as LinkIcon, Plus, RefreshCw, Send, Trash2 } from "lucide-react";
import { useApp } from "../store";
import { useNav } from "../nav";
import { useActing } from "../acting";
import { api, errText } from "../api";
import { Badge, Button, Card, Empty, Field, Hint, Input, Row, Spinner } from "../components/ui";
import type { Activation, AgencyActivity, AgencyDraftOut, AgencyOut, AgencyPayment, AgencyUsage, PaymentsSummary } from "../types";
import { copyText, fmtAmount, fmtDate } from "../utils";

// ── Наблюдение за агентствами: «светофор» + относительное время ──────
function engagementMeta(eng: string): { dot: string; labelKey: string } {
  switch (eng) {
    case "active":
      return { dot: "bg-emerald-500", labelKey: "engActive" };
    case "quiet":
      return { dot: "bg-amber-500", labelKey: "engQuiet" };
    case "asleep":
      return { dot: "bg-rose-500", labelKey: "engAsleep" };
    default:
      return { dot: "bg-slate-400", labelKey: "engNew" };
  }
}

function fmtAgo(iso: string | null | undefined, t: (k: string) => string): string {
  if (!iso) return "—";
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return "—";
  const min = Math.floor((Date.now() - ts) / 60000);
  if (min < 60) return t("agoJustNow");
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} ${t("agoHours")}`;
  const d = Math.floor(h / 24);
  if (d === 1) return t("agoYesterday");
  return `${d} ${t("agoDays")}`;
}

// Маленький блок «число + подпись» (для Сегодня/Вчера/Позавчера).
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
        <div className="h-full bg-primary/70" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// Подробный отчёт об активности агентства (внутри карточки агентства).
function AgencyActivityPanel({ id }: { id: number }) {
  const { t } = useApp();
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
                className="w-full rounded-t bg-primary/70"
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
          <SrcBar label={t("addChannel")} v={a.source_channel} total={srcTotal} />
        </Card>
      )}

      {/* Активность команды */}
      <Card className="mt-2">
        <div className="font-bold mb-1">{t("teamActivity")}</div>
        <Row label={`${t("actLogins")} (7 / 30)`} value={`${a.logins_7d} / ${a.logins_30d}`} />
        <Row label={t("actActiveUsers")} value={`${a.active_users} / ${a.total_users}`} />
        <Row label={t("lastActivity")} value={fmtAgo(a.last_activity_at, t)} />
      </Card>

      {/* По сотрудникам */}
      {a.employees.length > 0 && (
        <Card className="mt-2">
          <div className="font-bold mb-1.5">{t("byEmployee")}</div>
          {a.employees.map((e) => (
            <div
              key={e.user_id ?? e.name}
              className="flex items-center justify-between py-1.5 border-b border-line last:border-0"
            >
              <span className="truncate font-medium">{e.name || "—"}</span>
              <span className="text-[12px] text-muted shrink-0 ml-2">
                +{e.added} · {e.last_login_at ? fmtAgo(e.last_login_at, t) : t("neverIn")}
              </span>
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
      <div className="mt-2 flex items-center justify-between gap-2 rounded-xl bg-primary-soft border border-primary/30 px-3 py-2">
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

// Свод использования по всем агентствам (вовлечённость + объекты).
function UsageSummary({ usage }: { usage: AgencyUsage[] }) {
  const { t } = useApp();
  const by = (e: string) => usage.filter((u) => u.engagement === e).length;
  const objects = usage.reduce((s, u) => s + u.objects_total, 0);
  const today = usage.reduce((s, u) => s + u.added_today, 0);
  const week = usage.reduce((s, u) => s + u.added_7d, 0);
  const dot = (c: string, k: string, n: number) => (
    <span className="inline-flex items-center gap-1">
      <span className={`w-2 h-2 rounded-full ${c}`} /> {t(k)} {n}
    </span>
  );
  return (
    <Card className="mt-3">
      <div className="font-extrabold mb-1.5">{t("usageTitle")}</div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[12.5px]">
        {dot("bg-emerald-500", "engActive", by("active"))}
        {dot("bg-amber-500", "engQuiet", by("quiet"))}
        {dot("bg-rose-500", "engAsleep", by("asleep"))}
        {dot("bg-slate-400", "engNew", by("new"))}
      </div>
      <div className="text-[12.5px] text-muted mt-1.5">
        {t("actObjects")}: {objects} · {t("actAddedDay")} +{today} · {t("actWeek")} +{week}
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
  const { t, lang } = useApp();
  const [items, setItems] = useState<AgencyPayment[] | null>(null);
  useEffect(() => {
    api<AgencyPayment[]>("/api/v1/agencies/" + id + "/payments").then((r) => {
      setItems(r.ok && Array.isArray(r.data) ? r.data : []);
    });
  }, [id, refresh]);
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
              <span className="font-extrabold text-primary">
                {p.amount != null ? `${fmtAmount(p.amount)} ${p.currency || ""}` : "—"}
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

export function AgenciesScreen() {
  const { t, lang, toast } = useApp();
  const nav = useNav();
  const [list, setList] = useState<AgencyOut[] | null>(null);
  const [usage, setUsage] = useState<Record<number, AgencyUsage>>({});
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    const r = await api<AgencyOut[]>("/api/v1/agencies");
    if (r.ok && Array.isArray(r.data)) {
      setList(r.data);
      setErr(null);
    } else setErr(`${t("notFound")} (${r.status})`);
    const u = await api<AgencyUsage[]>("/api/v1/agencies/usage");
    if (u.ok && Array.isArray(u.data)) {
      setUsage(Object.fromEntries(u.data.map((x) => [x.agency_id, x])));
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const usageList = Object.values(usage);

  return (
    <div>
      <Button full onClick={() => nav.push({ name: "agencyCreate" })}>
        <Plus size={18} /> {t("createAgency")}
      </Button>
      {usageList.length > 0 && <UsageSummary usage={usageList} />}
      <RevenuePanel />
      <div className="mt-3">
        {err ? (
          <Empty>{err}</Empty>
        ) : !list ? (
          <Spinner />
        ) : !list.length ? (
          <Empty icon={<Building2 size={24} />}>{t("noAgencies")}</Empty>
        ) : (
          list.map((a) => {
            const adminTxt = a.admin_name
              ? a.admin_name + (a.admin_telegram_id ? ` (ID ${a.admin_telegram_id})` : "")
              : t("notAssigned");
            const u = usage[a.id];
            const meta = u ? engagementMeta(u.engagement) : null;
            return (
              <button
                key={a.id}
                onClick={() => nav.push({ name: "agencyManage", id: a.id })}
                className="w-full text-left mt-2.5 rounded-xl2 bg-card border border-line shadow-soft p-4 transition active:scale-[.99] hover:shadow-lg2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-extrabold">{a.name}</span>
                  {statusBadge(a, t)}
                </div>
                {u && meta && (
                  <div className="text-[13px] mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                    <span className="inline-flex items-center gap-1.5 font-bold">
                      <span className={`w-2 h-2 rounded-full ${meta.dot}`} />
                      {t(meta.labelKey)}
                    </span>
                    <span className="text-muted">· {u.objects_total} {t("actObjects").toLowerCase()}</span>
                    <span className="text-muted">· {t("actAddedDay")} +{u.added_today}</span>
                    {u.last_activity_at && <span className="text-muted">· {fmtAgo(u.last_activity_at, t)}</span>}
                  </div>
                )}
                {a.project_name && (
                  <div className="text-[13px] text-muted mt-1">
                    {t("projectName")}: {a.project_name}
                  </div>
                )}
                <div className="text-[13px] text-muted">
                  ID {a.id} · {t("subUntil")}: {fmtDate(a.subscription_expires_at, lang)}
                </div>
                <div className="text-[13px] text-muted">
                  {t("admin")}: {adminTxt}
                </div>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

// ── Личные агентства владельца платформы ────────────────────────────────────
// Здесь владелец создаёт СВОИ агентства (где он сам — главный админ) и «входит»
// в них, получая обычный интерфейс агентства. Создание — через простой prompt,
// чтобы не плодить отдельный экран (нужно только название).
export function MyAgenciesScreen() {
  const { t, toast } = useApp();
  const nav = useNav();
  const { enterAgency } = useActing();
  const [list, setList] = useState<AgencyOut[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
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
    const v = window.prompt(t("personalAgencyNamePrompt"), "");
    if (v === null) return;
    if (!v.trim()) {
      toast(t("emptyName"), "warn");
      return;
    }
    setBusy(true);
    const r = await api("/api/v1/agencies/mine", { method: "POST", body: { name: v.trim() } });
    setBusy(false);
    if (r.ok) {
      toast(t("agencyCreated"), "ok");
      load();
    } else toast(errText(r.data, r.status), "err");
  }

  async function enter(id: number) {
    const ok = await enterAgency(id);
    if (ok) nav.resetTo({ name: "home" });
  }

  return (
    <div>
      <Button full disabled={busy} onClick={create}>
        <Plus size={18} /> {t("createPersonalAgency")}
      </Button>
      <div className="mt-3">
        {err ? (
          <Empty>{err}</Empty>
        ) : !list ? (
          <Spinner />
        ) : !list.length ? (
          <Empty icon={<Briefcase size={24} />}>{t("noPersonalAgencies")}</Empty>
        ) : (
          list.map((a) => (
            <div
              key={a.id}
              className="mt-2.5 rounded-xl2 bg-card border border-line shadow-soft p-4"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-extrabold">{a.name}</span>
                <Button size="sm" onClick={() => enter(a.id)}>
                  {t("enterAgency")}
                </Button>
              </div>
              {a.project_name && (
                <div className="text-[13px] text-muted mt-1">
                  {t("projectName")}: {a.project_name}
                </div>
              )}
              <div className="text-[13px] text-muted">ID {a.id}</div>
            </div>
          ))
        )}
      </div>
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
    setSaving(true);
    const parsedDays = parseInt(days, 10);
    const body: Record<string, unknown> = {
      name: name.trim(),
      subscription_days: Number.isNaN(parsedDays) ? 30 : parsedDays,
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
          <AgencyActivityPanel id={id} />
          <PaymentHistory id={id} refresh={payKey} />
        </>
      )}
    </div>
  );
}
