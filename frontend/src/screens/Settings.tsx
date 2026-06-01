import { useState } from "react";
import { useApp } from "../store";
import { api, errText } from "../api";
import { Button, Card, Field, Hint, Input, Label, Segmented, SectionTitle, Select } from "../components/ui";
import { CURRENCIES, Lang } from "../i18n";
import type { AgencySettings } from "../types";

export function SettingsScreen() {
  const { t, lang, theme, setLang, setTheme, user, settings, setSettings, clearAuth, toast } = useApp();
  const role = user?.role;
  const isOwnerAdmin = role === "agency_admin" && !!user?.is_owner;

  const [projectName, setProjectName] = useState(settings?.project_name || "");
  const [contactPhone, setContactPhone] = useState(settings?.contact_phone || "");
  const [currency, setCurrency] = useState(settings?.default_currency || "USD");
  const [notify, setNotify] = useState<"on" | "off">(settings?.notify_new_objects ? "on" : "off");
  const [saving, setSaving] = useState(false);

  async function saveAgency() {
    setSaving(true);
    const r = await api<AgencySettings>("/api/v1/agency/settings", {
      method: "PATCH",
      body: {
        project_name: projectName.trim(),
        contact_phone: contactPhone.trim(),
        default_currency: currency,
        notify_new_objects: notify === "on",
      },
    });
    setSaving(false);
    if (r.ok && r.data) {
      setSettings(r.data);
      toast(t("saved"), "ok");
    } else toast(errText(r.data, r.status), "err");
  }

  async function transfer() {
    const idStr = window.prompt(t("transferPrompt"), "");
    if (idStr === null) return;
    const tgId = parseInt(idStr.trim(), 10);
    if (Number.isNaN(tgId)) {
      toast(t("badId"), "warn");
      return;
    }
    const username = window.prompt(t("transferUserPrompt"), "");
    if (username === null) return;
    const uname = username.trim();

    // Шаг 1: запросить код подтверждения (придёт в чат с ботом).
    const reqBody: Record<string, unknown> = { new_telegram_id: tgId };
    if (uname) reqBody.new_username = uname;
    const r1 = await api("/api/v1/platform/transfer-request", { method: "POST", body: reqBody });
    if (!r1.ok) {
      toast(errText(r1.data, r1.status), "err");
      return;
    }
    toast(t("codeSent"), "info");

    // Шаг 2: ввести код из бота и подтвердить.
    const code = window.prompt(t("enterCode"), "");
    if (code === null || !code.trim()) return;
    if (!window.confirm(t("transferConfirm2"))) return;
    const body: Record<string, unknown> = { new_telegram_id: tgId, code: code.trim() };
    if (uname) body.new_username = uname;
    const r = await api("/api/v1/platform/transfer-ownership", { method: "POST", body });
    if (r.ok) {
      toast(t("transferred"), "ok");
      setTimeout(() => clearAuth(), 800);
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
            <Field label={t("defaultCurrency")}>
              <Select value={currency} onChange={(e) => setCurrency(e.target.value)}>
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="mt-3">
              <Label>{t("notifyNewObjects")}</Label>
              <Segmented
                value={notify}
                onChange={(v) => setNotify(v)}
                options={[
                  { value: "off", label: t("notifyOff") },
                  { value: "on", label: t("notifyOn") },
                ]}
              />
              <Hint>{t("notifyNewObjectsHint")}</Hint>
            </div>
            <Button full className="mt-4" disabled={saving} onClick={saveAgency}>
              {t("saveSettings")}
            </Button>
          </Card>
        </div>
      )}

      {role === "superadmin" && (
        <div className="mt-2">
          <SectionTitle>{t("platformSection")}</SectionTitle>
          <Button full variant="danger" onClick={transfer}>
            {t("transferOwnership")}
          </Button>
        </div>
      )}
    </div>
  );
}
