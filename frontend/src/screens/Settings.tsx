import { useEffect, useRef, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { useApp } from "../store";
import { api, apiUpload, errText, type ApiResult } from "../api";
import { Button, Card, Field, Hint, Input, Label, Segmented, Select, SectionTitle } from "../components/ui";
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

// ── Импорт готовой базы клиента из файла (.xlsx/.csv) ───────────────
type ImportTargetField = { code: string; label: string };
type ImportAnalysis = {
  columns: string[];
  sample_rows: string[][];
  total_rows: number;
  suggested_mapping: Record<string, number | null>;
  target_fields: ImportTargetField[];
};

function BaseImportCard() {
  const { t, toast } = useApp();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<ImportAnalysis | null>(null);
  const [mapping, setMapping] = useState<Record<string, number | null>>({});
  const [busy, setBusy] = useState(false);

  function reset() {
    setFile(null);
    setAnalysis(null);
    setMapping({});
    if (fileRef.current) fileRef.current.value = "";
  }

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setBusy(true);
    const form = new FormData();
    form.append("file", f);
    const r = await apiUpload<ImportAnalysis>("/api/v1/imports/base/analyze", form);
    setBusy(false);
    if (r.ok && r.data) {
      setAnalysis(r.data);
      setMapping({ ...r.data.suggested_mapping });
    } else {
      toast(errText(r.data, r.status), "err");
      reset();
    }
  }

  async function run() {
    if (!file) return;
    setBusy(true);
    const form = new FormData();
    form.append("file", file);
    form.append("mapping", JSON.stringify(mapping));
    const r = await apiUpload<{ created: number; skipped: number; failed: number }>(
      "/api/v1/imports/base/commit",
      form
    );
    setBusy(false);
    if (r.ok && r.data) {
      const d = r.data;
      const parts = [`${t("baseImportCreated")}: ${d.created}`, `${t("baseImportSkipped")}: ${d.skipped}`];
      if (d.failed) parts.push(`${t("baseImportFailed")}: ${d.failed}`);
      toast(parts.join(", "), d.created > 0 ? "ok" : "err");
      reset();
    } else {
      toast(errText(r.data, r.status), "err");
    }
  }

  const colLabel = (i: number) => analysis?.columns[i]?.trim() || `#${i + 1}`;

  return (
    <div className="mt-2">
      <SectionTitle>{t("baseImportTitle")}</SectionTitle>
      <Card>
        {!analysis ? (
          <>
            <Hint>{t("baseImportHint")}</Hint>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.csv,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className="hidden"
              onChange={onPick}
            />
            <Button full className="mt-3" disabled={busy} onClick={() => fileRef.current?.click()}>
              {busy ? t("baseImportAnalyzing") : t("baseImportChoose")}
            </Button>
          </>
        ) : (
          <>
            <div className="text-[13px] text-muted mb-1">
              {t("baseImportRowsFound")}: {analysis.total_rows}
            </div>
            <Hint>{t("baseImportMapHint")}</Hint>
            <div className="mt-2 space-y-2">
              {analysis.target_fields.map((tf) => (
                <div key={tf.code} className="flex items-center gap-2">
                  <div className="w-[42%] text-[13px] shrink-0">{tf.label}</div>
                  <Select
                    className="flex-1"
                    value={mapping[tf.code] ?? ""}
                    onChange={(e) =>
                      setMapping((m) => ({
                        ...m,
                        [tf.code]: e.target.value === "" ? null : Number(e.target.value),
                      }))
                    }
                  >
                    <option value="">{t("baseImportColNone")}</option>
                    {analysis.columns.map((_, i) => (
                      <option key={i} value={i}>
                        {colLabel(i)}
                      </option>
                    ))}
                  </Select>
                </div>
              ))}
            </div>

            {analysis.sample_rows.length > 0 && (
              <div className="mt-3">
                <Label>{t("baseImportPreview")}</Label>
                <div className="overflow-x-auto rounded-lg border border-black/10 dark:border-white/10">
                  <table className="text-[11px] whitespace-nowrap">
                    <thead>
                      <tr className="bg-black/5 dark:bg-white/5">
                        {analysis.columns.map((c, i) => (
                          <th key={i} className="px-2 py-1 text-left font-semibold">{c?.trim() || `#${i + 1}`}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {analysis.sample_rows.map((row, ri) => (
                        <tr key={ri} className="border-t border-black/5 dark:border-white/5">
                          {analysis.columns.map((_, ci) => (
                            <td key={ci} className="px-2 py-1 text-muted max-w-[160px] truncate">{row[ci] || ""}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <Button full className="mt-4" disabled={busy} onClick={run}>
              {busy ? t("baseImportRunning") : t("baseImportRun")}
            </Button>
            <Button full variant="ghost" className="mt-2" disabled={busy} onClick={reset}>
              {t("baseImportReset")}
            </Button>
          </>
        )}
      </Card>
    </div>
  );
}

// ── Односторонний экспорт базы в файл Excel (.xlsx) ─────────────────
function ExcelExportCard() {
  const { t, toast } = useApp();
  const [busy, setBusy] = useState(false);

  async function download() {
    setBusy(true);
    // В Telegram файл нельзя качать «изнутри» (webview зависает) — берём короткую
    // ссылку и открываем во внешнем браузере, который и скачивает .xlsx.
    const r = await api<{ url: string }>("/api/v1/exports/excel/link", { method: "POST" });
    setBusy(false);
    if (r.ok && r.data?.url) openLink(r.data.url);
    else toast(errText(r.data, r.status) || t("excelError"), "err");
  }

  return (
    <div className="mt-2">
      <SectionTitle>{t("excelTitle")}</SectionTitle>
      <Card>
        <Hint>{t("excelHint")}</Hint>
        <Button full className="mt-3" disabled={busy} onClick={download}>
          {busy ? t("excelDownloading") : t("excelDownload")}
        </Button>
      </Card>
    </div>
  );
}

// ── Массовый импорт из открытого Telegram-канала (постранично) ──────
type TgScanOut = {
  channel: string;
  created: number;
  skipped: number;
  scanned: number;
  next_before: number | null;
  done: boolean;
};

function TelegramImportCard() {
  const { t, toast } = useApp();
  const [channel, setChannel] = useState("");
  const [running, setRunning] = useState(false);
  const [scanned, setScanned] = useState(0);
  const [created, setCreated] = useState(0);
  const stopRef = useRef(false);

  // Предохранитель: не уходим в бесконечность на гигантских каналах.
  const HARD_CAP = 600;

  async function start() {
    if (!channel.trim() || running) return;
    stopRef.current = false;
    setRunning(true);
    setScanned(0);
    setCreated(0);
    let before: number | null = null;
    let totalScanned = 0;
    let totalCreated = 0;
    let failed = false;
    while (!stopRef.current && totalScanned < HARD_CAP) {
      const r: ApiResult<TgScanOut> = await api<TgScanOut>("/api/v1/imports/telegram/scan", {
        method: "POST",
        body: { channel: channel.trim(), before },
        timeoutMs: 120000,
      });
      if (!r.ok || !r.data) {
        toast(errText(r.data, r.status) || t("tgImportError"), "err");
        failed = true;
        break;
      }
      totalScanned += r.data.scanned;
      totalCreated += r.data.created;
      setScanned(totalScanned);
      setCreated(totalCreated);
      if (r.data.done || r.data.next_before == null) break;
      before = r.data.next_before;
    }
    setRunning(false);
    if (!failed) toast(`${t("tgImportDoneMsg")}: ${totalCreated}`, totalCreated > 0 ? "ok" : "err");
  }

  return (
    <div className="mt-2">
      <SectionTitle>{t("tgImportTitle")}</SectionTitle>
      <Card>
        <Hint>{t("tgImportHint")}</Hint>
        <Input
          className="mt-3"
          placeholder={t("tgImportPlaceholder")}
          value={channel}
          onChange={(e) => setChannel(e.target.value)}
          disabled={running}
        />
        {(running || scanned > 0) && (
          <div className="mt-3 text-[13px] text-muted">
            {t("tgImportScanned")}: <b>{scanned}</b> · {t("tgImportCreated")}: <b>{created}</b>
          </div>
        )}
        {!running ? (
          <Button full className="mt-3" disabled={!channel.trim()} onClick={start}>
            {t("tgImportStart")}
          </Button>
        ) : (
          <Button full variant="danger" className="mt-3" onClick={() => (stopRef.current = true)}>
            {t("tgImportStop")}
          </Button>
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
          <BaseImportCard />
          <ExcelExportCard />
          <TelegramImportCard />
        </div>
      )}

      <div className="mt-6 text-center text-[11px] text-muted/70 select-text">
        {t("version")}: {__BUILD_ID__}
      </div>
    </div>
  );
}
