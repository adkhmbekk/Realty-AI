import { useEffect, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { useApp } from "../store";
import { api, errText } from "../api";
import { Button, Card, Field, Hint, Input, Label, Segmented, SectionTitle } from "../components/ui";
import { Lang } from "../i18n";
import type { AgencySettings, SheetStatus } from "../types";
import { confirmDialog, openLink } from "../telegram";

// ── Карточка подключения Google Sheets (только для главного админа) ──
function GoogleSheetsCard() {
  const { t, toast } = useApp();
  const [st, setSt] = useState<SheetStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("Realty AI — База объектов");

  async function load() {
    const r = await api<SheetStatus>("/api/v1/sheets/status");
    if (r.ok && r.data) setSt(r.data);
  }
  useEffect(() => {
    load();
  }, []);

  async function connect() {
    setBusy(true);
    const r = await api<{ auth_url: string }>("/api/v1/sheets/connect", { method: "POST" });
    setBusy(false);
    if (r.ok && r.data?.auth_url) openLink(r.data.auth_url);
    else toast(errText(r.data, r.status), "err");
  }
  async function create() {
    setBusy(true);
    const r = await api<{ spreadsheet_url: string }>("/api/v1/sheets/create", { method: "POST", body: { title } });
    setBusy(false);
    if (r.ok) {
      toast(t("sheetsDone"), "ok");
      load();
    } else toast(errText(r.data, r.status), "err");
  }
  async function syncNow() {
    setBusy(true);
    const r = await api("/api/v1/sheets/sync", { method: "POST" });
    setBusy(false);
    if (r.ok) toast(t("sheetsSynced"), "ok");
    else toast(errText(r.data, r.status), "err");
  }
  async function exportNow() {
    setBusy(true);
    const r = await api("/api/v1/sheets/export", { method: "POST" });
    setBusy(false);
    if (r.ok) toast(t("sheetsExported"), "ok");
    else toast(errText(r.data, r.status), "err");
  }
  async function disconnect() {
    if (!(await confirmDialog(t("sheetsDisconnectQ")))) return;
    setBusy(true);
    const r = await api("/api/v1/sheets/disconnect", { method: "POST" });
    setBusy(false);
    if (r.ok) {
      setSt({ connected: false, status: "disconnected", has_spreadsheet: false });
      load();
    } else toast(errText(r.data, r.status), "err");
  }

  return (
    <div className="mt-2">
      <SectionTitle>{t("sheetsTitle")}</SectionTitle>
      <Card>
        {!st?.connected ? (
          <>
            <Hint>{t("sheetsHint")}</Hint>
            <Button full className="mt-3" disabled={busy} onClick={connect}>
              {t("sheetsConnect")}
            </Button>
            <Hint>{t("sheetsConnectHint")}</Hint>
            <Button full variant="ghost" className="mt-2" onClick={load}>
              {t("sheetsCheckAgain")}
            </Button>
          </>
        ) : !st?.has_spreadsheet ? (
          <>
            <div className="text-[13px] font-bold text-emerald-600 dark:text-emerald-400 mb-1 flex items-center gap-1.5">
              <CheckCircle2 size={15} /> {t("sheetsConnected")}
            </div>
            <Field label={t("sheetsCreateTitle")}>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} />
            </Field>
            <Button full className="mt-3" disabled={busy} onClick={create}>
              {busy ? t("sheetsCreating") : t("sheetsCreate")}
            </Button>
            <Button full variant="ghost" className="mt-2" onClick={disconnect}>
              {t("sheetsDisconnect")}
            </Button>
          </>
        ) : (
          <>
            {st.sheet_title && <div className="text-[13px] text-muted mb-2">{st.sheet_title}</div>}
            <Button full onClick={() => st.spreadsheet_url && openLink(st.spreadsheet_url)}>
              {t("sheetsOpen")}
            </Button>
            <Button full variant="ghost" className="mt-2" disabled={busy} onClick={syncNow}>
              {busy ? t("sheetsSyncing") : t("sheetsSync")}
            </Button>
            <Hint>{t("sheetsSyncHint")}</Hint>
            <Button full variant="ghost" className="mt-2" disabled={busy} onClick={exportNow}>
              {busy ? t("sheetsExporting") : t("sheetsExport")}
            </Button>
            <Button full variant="ghost" className="mt-2" onClick={disconnect}>
              {t("sheetsDisconnect")}
            </Button>
          </>
        )}
      </Card>
    </div>
  );
}

export function SettingsScreen() {
  const { t, lang, theme, setLang, setTheme, user, settings, setSettings, toast } = useApp();
  const role = user?.role;
  const isOwnerAdmin = role === "agency_admin" && !!user?.is_owner;

  const [projectName, setProjectName] = useState(settings?.project_name || "");
  const [contactPhone, setContactPhone] = useState(settings?.contact_phone || "");
  const [saving, setSaving] = useState(false);

  async function saveAgency() {
    setSaving(true);
    const r = await api<AgencySettings>("/api/v1/agency/settings", {
      method: "PATCH",
      body: {
        project_name: projectName.trim(),
        contact_phone: contactPhone.trim(),
      },
    });
    setSaving(false);
    if (r.ok && r.data) {
      setSettings(r.data);
      toast(t("saved"), "ok");
    } else toast(errText(r.data, r.status), "err");
  }

  const langOpts: { value: Lang; label: string }[] = [
    { value: "ru", label: t("lang_ru") },
    { value: "uz", label: t("lang_uz") },
    { value: "en", label: t("lang_en") },
  ];

  return (
    <div>
      <Label>{t("language")}</Label>
      <Segmented value={lang} onChange={(v) => setLang(v)} options={langOpts} />

      <div className="mt-3">
        <Label>{t("theme")}</Label>
        <Segmented
          value={theme}
          onChange={(v) => setTheme(v)}
          options={[
            { value: "light", label: "☀️ " + t("themeLight") },
            { value: "dark", label: "🌙 " + t("themeDark") },
          ]}
        />
      </div>
      <Hint>{t("settingsHint")}</Hint>

      {isOwnerAdmin && (
        <div className="mt-2">
          <SectionTitle>{t("agencyLbl")}</SectionTitle>
          <Card>
            <Field label={t("projectName")}>
              <Input value={projectName} onChange={(e) => setProjectName(e.target.value)} />
            </Field>
            <Hint>{t("projectNameHint")}</Hint>
            <Field label={t("contactPhone")}>
              <Input value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} />
            </Field>
            <Hint>{t("contactPhoneHint")}</Hint>
            <Button full className="mt-4" disabled={saving} onClick={saveAgency}>
              {t("saveSettings")}
            </Button>
          </Card>
          <GoogleSheetsCard />
        </div>
      )}
    </div>
  );
}
