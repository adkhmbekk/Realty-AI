import { useApp } from "../store";
import { Card, Row, Hint } from "../components/ui";
import { fmtDate, daysLeft } from "../utils";

export function ProfileScreen() {
  const { t, L, lang, user, settings } = useApp();
  if (!user) return null;
  return (
    <div>
      <Card>
        <Row label={t("name")} value={user.full_name || t("notSet")} />
        <Row label={t("username")} value={user.username ? "@" + user.username : t("notSet")} />
        <Row label={t("roleLbl")} value={L.roleLabel(user.role)} />
        <Row label={t("tgId")} value={user.telegram_id} />
      </Card>
      {settings?.project_name && (
        <Hint>
          {t("projectName")}: {settings.project_name}
        </Hint>
      )}
      {user.is_owner && settings?.subscription_expires_at && (
        <Card className="mt-3">
          <Row label={t("subUntil")} value={fmtDate(settings.subscription_expires_at, lang, settings.timezone)} />
          <Row label={t("daysLeft")} value={daysLeft(settings.subscription_expires_at)} />
        </Card>
      )}
    </div>
  );
}

export function SuspendedScreen() {
  const { t, L, user } = useApp();
  return (
    <div>
      {user && (
        <Card>
          <Row label={t("name")} value={user.full_name || t("notSet")} />
          <Row label={t("roleLbl")} value={L.roleLabel(user.role)} />
        </Card>
      )}
      <div className="mt-3 rounded-[14px] px-3.5 py-3 text-sm leading-relaxed bg-rose-500/10 text-rose-600 dark:text-rose-300 border border-rose-500/30">
        {t("suspendedMsg")}
      </div>
    </div>
  );
}
