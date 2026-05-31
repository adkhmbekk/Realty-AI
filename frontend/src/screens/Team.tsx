import { useEffect, useState } from "react";
import { useApp } from "../store";
import { api, errText } from "../api";
import { Badge, Button, Card, Empty, Spinner } from "../components/ui";
import type { Member } from "../types";

export function TeamScreen() {
  const { t, L, user, toast } = useApp();
  const [members, setMembers] = useState<Member[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const meOwner = !!user?.is_owner;

  async function load() {
    const r = await api<Member[]>("/api/v1/team");
    if (r.ok && Array.isArray(r.data)) {
      setMembers(r.data);
      setErr(null);
    } else setErr(`${t("notFound")} (${r.status})`);
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function toggleActive(m: Member) {
    const r = await api("/api/v1/team/" + m.id, { method: "PATCH", body: { is_active: !m.is_active } });
    if (r.ok) {
      toast(t("done"), "ok");
      load();
    } else toast(errText(r.data, r.status), "err");
  }
  async function changeRole(m: Member) {
    const next = m.role === "agency_admin" ? "agent" : "agency_admin";
    const roleName = next === "agency_admin" ? t("role_agency_admin") : t("role_agent");
    if (!window.confirm(t("roleQ") + roleName + "»?")) return;
    const r = await api("/api/v1/team/" + m.id, { method: "PATCH", body: { role: next } });
    if (r.ok) {
      toast(t("roleChanged"), "ok");
      load();
    } else toast(errText(r.data, r.status), "err");
  }
  async function makeOwner(m: Member) {
    if (!window.confirm(t("makeOwnerQ"))) return;
    const r = await api("/api/v1/team/" + m.id + "/owner", { method: "POST" });
    if (r.ok) {
      toast(t("ownerTransferred"), "ok");
      load();
    } else toast(errText(r.data, r.status), "err");
  }

  if (err) return <Empty>{err}</Empty>;
  if (!members) return <Spinner />;
  if (!members.length) return <Empty>{t("noMembers")}</Empty>;

  return (
    <div>
      {members.map((m) => {
        const isSelf = user && m.id === user.id;
        const name = m.full_name || (m.username ? "@" + m.username : "ID " + m.telegram_id);
        const canAct = !isSelf && !m.is_owner && (m.role === "agent" || meOwner);
        return (
          <Card key={m.id} className="mt-2.5">
            <div className="flex items-center justify-between gap-2">
              <span className="font-extrabold">{name}</span>
              <span className="flex gap-1.5">
                {m.is_owner && <Badge color="amber">{t("mainAdmin")}</Badge>}
                <Badge color={m.is_active ? "green" : "gray"}>{m.is_active ? t("mActive") : t("mDisabled")}</Badge>
              </span>
            </div>
            <div className="text-[13px] text-muted mt-1">
              {L.roleLabel(m.role)}
              {m.username ? " · @" + m.username : ""}
            </div>
            <div className="mt-2 flex gap-1.5 flex-wrap">
              {isSelf ? (
                <Badge color="gray">{t("itsYou")}</Badge>
              ) : canAct ? (
                <>
                  <Button size="sm" variant={m.is_active ? "danger" : "ghost"} onClick={() => toggleActive(m)}>
                    {m.is_active ? t("disable") : t("enable")}
                  </Button>
                  {meOwner && (
                    <>
                      <Button size="sm" variant="ghost" onClick={() => changeRole(m)}>
                        {m.role === "agency_admin" ? t("demote") : t("promote")}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => makeOwner(m)}>
                        {t("makeOwner")}
                      </Button>
                    </>
                  )}
                </>
              ) : null}
            </div>
          </Card>
        );
      })}
    </div>
  );
}
