import { useEffect, useState } from "react";
import { useApp } from "../store";
import { api, errText } from "../api";
import { Badge, Button, Card, Empty, Field, Input, Select, SectionTitle, Spinner } from "../components/ui";
import type { Invite } from "../types";
import { copyText } from "../utils";
import { haptic, shareToTelegram } from "../telegram";
import { Send } from "lucide-react";

export function InvitesScreen() {
  const { t, L, toast, user } = useApp();
  // Обычный админ (не владелец) может приглашать только агентов; роль админа
  // в приглашении доступна лишь главному админу.
  const canInviteAdmin = !!user?.is_owner;

  // Поделиться приглашением: открывает родной диалог Telegram — пользователь
  // выбирает ОДНОГО получателя. Отправляем готовую ссылку + код.
  function shareInvite(inv: { join_link?: string | null; code: string }) {
    haptic();
    const link = inv.join_link || "";
    const txt = t("inviteShareText") + (link ? "\n" + link : "") + "\n" + t("codeLbl") + ": " + inv.code;
    shareToTelegram(txt);
  }
  const [role, setRole] = useState("agent");
  const [days, setDays] = useState("7");
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<Invite | null>(null);
  const [list, setList] = useState<Invite[] | null>(null);

  async function load() {
    const r = await api<Invite[]>("/api/v1/invites");
    if (r.ok && Array.isArray(r.data)) setList(r.data);
    else setList([]);
  }
  useEffect(() => {
    load();
  }, []);

  async function create() {
    setCreating(true);
    const r = await api<Invite>("/api/v1/invites", { method: "POST", body: { role, expires_in_days: parseInt(days, 10) || 7 } });
    setCreating(false);
    if (r.ok && r.data) {
      toast(t("inviteCreated"), "ok");
      setCreated(r.data);
      load();
    } else toast(errText(r.data, r.status), "err");
  }
  async function revoke(inv: Invite) {
    const r = await api("/api/v1/invites/" + inv.id, { method: "DELETE" });
    if (r.ok) {
      toast(t("revoked"), "ok");
      load();
    } else toast(errText(r.data, r.status), "err");
  }

  const stMap: Record<string, { c: "green" | "gray" | "amber"; k: string }> = {
    active: { c: "green", k: "inv_active" },
    used: { c: "gray", k: "inv_used" },
    expired: { c: "amber", k: "inv_expired" },
  };

  return (
    <div>
      <Card>
        {canInviteAdmin ? (
          <Field label={t("inviteRole")}>
            <Select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="agent">{t("role_agent")}</option>
              <option value="agency_admin">{t("role_agency_admin")}</option>
            </Select>
          </Field>
        ) : (
          <Field label={t("inviteRole")}>
            <div className="px-3.5 py-3 rounded-[14px] bg-[var(--soft)] border border-line text-[15px] text-muted">
              {t("role_agent")}
            </div>
          </Field>
        )}
        <Field label={t("inviteDays")}>
          <Input inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value)} />
        </Field>
        <Button full className="mt-4" disabled={creating} onClick={create}>
          {t("createInvite")}
        </Button>
      </Card>

      {created && (
        <Card className="mt-3">
          <div className="text-[13px] text-muted">{t("giveToEmployee")}</div>
          {created.join_link && (
            <div className="mt-2 rounded-[12px] bg-slate-900 text-slate-100 px-3 py-2.5 text-[13px] font-mono break-all">
              {created.join_link}
            </div>
          )}
          <div className="text-[13px] text-muted mt-2">{t("codeLbl")}:</div>
          <div className="mt-1 rounded-[12px] bg-slate-900 text-slate-100 px-3 py-2.5 text-[13px] font-mono break-all">
            {created.code}
          </div>
          <Button full className="mt-3" onClick={() => shareInvite(created)}>
            <Send size={16} /> {t("shareInviteBtn")}
          </Button>
          <div className="mt-2 flex gap-1.5 flex-wrap">
            {created.join_link && (
              <Button size="sm" variant="ghost" onClick={async () => toast((await copyText(created.join_link!)) ? t("copied") : t("copy"), "ok")}>
                {t("copyLink")}
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={async () => toast((await copyText(created.code)) ? t("copied") : t("copy"), "ok")}>
              {t("copyCode")}
            </Button>
          </div>
        </Card>
      )}

      <div className="mt-4">
        <SectionTitle>{t("issuedInvites")}</SectionTitle>
        {!list ? (
          <Spinner />
        ) : !list.length ? (
          <Empty>{t("noInvites")}</Empty>
        ) : (
          list.map((inv) => {
            const st = stMap[inv.status] || { c: "gray" as const, k: inv.status };
            return (
              <Card key={inv.id} className="mt-2.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-extrabold">{L.roleLabel(inv.role)}</span>
                  <Badge color={st.c}>{stMap[inv.status] ? t(st.k) : inv.status}</Badge>
                </div>
                <div className="text-[13px] text-muted mt-1 break-all">
                  {t("codeLbl")}: {inv.code}
                </div>
                <div className="mt-2 flex gap-1.5">
                  <Button size="sm" variant="ghost" onClick={() => shareInvite(inv)}>
                    <Send size={14} /> {t("shareInviteBtn")}
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => revoke(inv)}>
                    {t("revoke")}
                  </Button>
                </div>
              </Card>
            );
          })
        )}
      </div>
    </div>
  );
}
