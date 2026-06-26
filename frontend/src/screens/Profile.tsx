import { User, LifeBuoy } from "lucide-react";
import { useApp } from "../store";
import { Card, Row, Hint, Button } from "../components/ui";
import { openTelegramLink } from "../telegram";
import { fmtDate, daysLeft, initials } from "../utils";

export function ProfileScreen() {
  const { t, L, lang, user, settings } = useApp();
  if (!user) return null;
  const displayName = user.full_name || (user.username ? "@" + user.username : t("notSet"));
  const supportUrl = settings?.support_url || null;
  return (
    <div>
      {/* Личная шапка с аватаром-инициалами */}
      <div
        className="flex items-center gap-3.5 rounded-xl3 p-4 mb-3 text-white overflow-hidden"
        style={{ background: "var(--grad-hero)", boxShadow: "0 16px 40px rgba(52,31,163,.36)" }}
      >
        <div className="w-14 h-14 shrink-0 rounded-2xl bg-white/20 border border-white/40 flex items-center justify-center text-xl font-extrabold backdrop-blur">
          {initials(user.full_name || user.username) || <User size={24} />}
        </div>
        <div className="min-w-0">
          <div className="text-[20px] font-extrabold leading-tight truncate">{displayName}</div>
          <div className="text-[13px] opacity-90 mt-0.5">{L.roleLabel(user.role, user.is_owner)}</div>
        </div>
      </div>
      <Card>
        <Row label={t("username")} value={user.username ? "@" + user.username : t("notSet")} />
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
      {/* Поддержка: связаться с нами (открывает чат в Telegram). */}
      {supportUrl && (
        <Card className="mt-3">
          <div className="flex items-center gap-2.5 mb-1.5">
            <LifeBuoy size={18} className="text-primary" />
            <span className="font-extrabold">{t("support")}</span>
          </div>
          <p className="text-[13px] text-muted mb-3">{t("supportText")}</p>
          <Button full size="sm" onClick={() => openTelegramLink(supportUrl)}>
            {t("contactSupport")}
          </Button>
        </Card>
      )}
      {/* Версия сборки — чтобы было видно, что приложение обновилось до свежей. */}
      <div className="text-center text-[11px] text-muted mt-5">
        {t("buildVersion")}: {__BUILD_ID__}
      </div>
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
          <Row label={t("roleLbl")} value={L.roleLabel(user.role, user.is_owner)} />
        </Card>
      )}
      <div className="mt-3 rounded-[14px] px-3.5 py-3 text-sm leading-relaxed bg-rose-500/10 text-rose-600 dark:text-rose-300 border border-rose-500/30">
        {t("suspendedMsg")}
      </div>
    </div>
  );
}
