import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { useApp } from "../store";
import { useNav } from "../nav";
import { api, errText } from "../api";
import { Badge, Button, Card, Empty, Field, Input, Row, Spinner } from "../components/ui";
import type { AgencyOut } from "../types";
import { fmtDate } from "../utils";

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
  };
  const m = map[eff] || { c: "gray" as const, k: eff };
  return <Badge color={m.c}>{map[eff] ? t(m.k) : eff}</Badge>;
}

export function AgenciesScreen() {
  const { t, lang, toast } = useApp();
  const nav = useNav();
  const [list, setList] = useState<AgencyOut[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    const r = await api<AgencyOut[]>("/api/v1/agencies");
    if (r.ok && Array.isArray(r.data)) {
      setList(r.data);
      setErr(null);
    } else setErr(`${t("notFound")} (${r.status})`);
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <Button full onClick={() => nav.push({ name: "agencyCreate" })}>
        <Plus size={18} /> {t("createAgency")}
      </Button>
      <div className="mt-3">
        {err ? (
          <Empty>{err}</Empty>
        ) : !list ? (
          <Spinner />
        ) : !list.length ? (
          <Empty>{t("noAgencies")}</Empty>
        ) : (
          list.map((a) => {
            const adminTxt = a.admin_name
              ? a.admin_name + (a.admin_telegram_id ? ` (ID ${a.admin_telegram_id})` : "")
              : t("notAssigned");
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

export function AgencyCreateScreen() {
  const { t, toast } = useApp();
  const nav = useNav();
  const [name, setName] = useState("");
  const [adminId, setAdminId] = useState("");
  const [adminUser, setAdminUser] = useState("");
  const [days, setDays] = useState("30");
  const [saving, setSaving] = useState(false);

  async function create() {
    if (!name.trim()) {
      toast(t("emptyName"), "warn");
      return;
    }
    const id = parseInt(adminId.trim(), 10);
    if (Number.isNaN(id)) {
      toast(t("badId"), "warn");
      return;
    }
    setSaving(true);
    const body: Record<string, unknown> = {
      name: name.trim(),
      admin_telegram_id: id,
      subscription_days: parseInt(days, 10) || 30,
    };
    const u = adminUser.trim();
    if (u) body.admin_username = u;
    const r = await api("/api/v1/agencies", { method: "POST", body });
    setSaving(false);
    if (r.ok) {
      toast(t("agencyCreated"), "ok");
      nav.pop();
    } else toast(errText(r.data, r.status), "err");
  }

  return (
    <Card>
      <Field label={t("agencyName")}>
        <Input value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label={t("adminTgId")}>
        <Input inputMode="numeric" value={adminId} onChange={(e) => setAdminId(e.target.value)} />
      </Field>
      <Field label={t("adminUsername")}>
        <Input value={adminUser} onChange={(e) => setAdminUser(e.target.value)} />
      </Field>
      <Field label={t("subDays")}>
        <Input inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value)} />
      </Field>
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
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    const r = await api<AgencyOut[]>("/api/v1/agencies");
    setLoading(false);
    if (r.ok && Array.isArray(r.data)) {
      const found = r.data.find((x) => x.id === id) || null;
      setA(found);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function sub(action: string, days?: number, expiresAt?: string) {
    const body: Record<string, unknown> = { action };
    if (days != null) body.days = days;
    if (expiresAt) body.expires_at = expiresAt;
    const r = await api("/api/v1/agencies/" + id + "/subscription", { method: "POST", body });
    if (r.ok) {
      toast(t("subUpdated"), "ok");
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
    sub("extend", d);
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
    if (!window.confirm(t("delAgQ1"))) return;
    if (!window.confirm(t("delAgQ2"))) return;
    const r = await api("/api/v1/agencies/" + id, { method: "DELETE" });
    if (r.ok) {
      toast(t("agDeleted"), "ok");
      nav.pop();
    } else toast(errText(r.data, r.status), "err");
  }

  return (
    <div>
      <Card>
        <div className="flex items-center justify-between gap-2 mb-1">
          <span className="text-[16px] font-extrabold">{a.name}</span>
          {statusBadge(a, t)}
        </div>
        {a.project_name && <Row label={t("projectName")} value={a.project_name} />}
        <Row label="ID" value={a.id} />
        <Row label={t("activatedAt")} value={fmtDate(a.activated_at || a.created_at, lang)} />
        <Row label={t("subUntil")} value={fmtDate(a.subscription_expires_at, lang)} />
        <Row label={t("admin")} value={adminTxt} />
      </Card>
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
        <Button full size="sm" variant={frozen ? "ghost" : "danger"} onClick={() => sub(frozen ? "activate" : "freeze")}>
          {frozen ? t("activate") : t("freeze")}
        </Button>
        <Button full size="sm" variant="danger" onClick={del}>
          {t("deleteAgency")}
        </Button>
      </div>
    </div>
  );
}
