import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, type Backup, type ImportFormat, type ImportReport } from "../api";
import { Link } from "react-router";
import { ErrorBox, Icon, formatDate, useToast } from "../components/ui";

const FORMATS: { key: ImportFormat; title: string; hint: string; accept: string }[] = [
  { key: "ai-learning-path", title: "AI learning path", hint: "path.json from your ai-learning-path folder. Modules become topics, in order.", accept: ".json,application/json" },
  { key: "learnmarks", title: "Learnmarks export", hint: "A file from “Download export” below — e.g. to move to a new laptop.", accept: ".json,application/json" },
  { key: "csv", title: "CSV list", hint: "Columns: url (required), title, topics, tags, status, priority, date_saved, description. Separate topics/tags with ; or |.", accept: ".csv,text/csv" },
];

export default function Settings() {
  return (
    <div className="flex flex-col gap-10">
      <section>
        <div className="lbl">System</div>
        <h1 className="mt-2 text-[44px] font-semibold leading-none tracking-[-0.035em]">
          Import · Backup · <span className="font-mono font-medium">Sync</span>
        </h1>
        <p className="mt-3 max-w-xl text-soft">
          Everything lives in one SQLite file on this laptop (<code className="font-mono text-sm">learnmarks/data/learnmarks.db</code>).
          Nothing is sent anywhere.
        </p>
      </section>
      <ImportPanel />
      <div className="grid grid-cols-[repeat(auto-fit,minmax(320px,1fr))] gap-5">
        <ExportPanel />
        <SyncPanel />
      </div>
      <BackupsPanel />
    </div>
  );
}

function readFile(file: File): Promise<string> {
  return file.text();
}

function ImportPanel() {
  const qc = useQueryClient();
  const toast = useToast();
  const [format, setFormat] = useState<ImportFormat>("ai-learning-path");
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const fmt = FORMATS.find((f) => f.key === format)!;

  async function body(): Promise<string> {
    const main = await readFile(file!);
    if (format !== "ai-learning-path" || !progress) return main;
    // path.json + the old syllabus page's progress, combined the way the importer expects.
    return JSON.stringify({ path: JSON.parse(main), progress: JSON.parse(await readFile(progress)) });
  }

  async function run(dryRun: boolean) {
    setBusy(true);
    setError(null);
    try {
      const r = await api.importFile(format, await body(), dryRun);
      setReport(r);
      if (!dryRun) {
        await qc.invalidateQueries();
        toast({ text: `Imported: ${r.summary.bookmarks_created} new bookmarks` });
      }
    } catch (e) {
      setReport(null);
      setError(e instanceof SyntaxError ? new Error(`Couldn't read the file as JSON: ${e.message}`) : e);
    } finally {
      setBusy(false);
    }
  }

  const reset = () => {
    setReport(null);
    setError(null);
  };

  return (
    <section className="flex flex-col gap-5 rounded-2xl border border-line bg-surface p-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-[-0.02em]">Import</h2>
        <p className="mt-1 text-sm text-soft">
          Preview first: nothing changes until you press <b>Import now</b>, and a backup is taken right before.
          Importing the same file again adds nothing. Bookmarks you already have keep their title, status and takeaway.
        </p>
      </div>

      <fieldset className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
        <legend className="lbl mb-2">Format</legend>
        {FORMATS.map((f) => (
          <label key={f.key}
            className={`flex cursor-pointer flex-col gap-1 rounded-xl border p-3.5 ${format === f.key ? "border-ink bg-hover" : "border-line hover:border-line-strong"}`}>
            <span className="flex items-center gap-2 font-semibold">
              <input type="radio" name="format" value={f.key} checked={format === f.key} className="accent-current"
                onChange={() => { setFormat(f.key); setFile(null); setProgress(null); reset(); }} />
              {f.title}
            </span>
            <span className="text-[13px] text-soft">{f.hint}</span>
          </label>
        ))}
      </fieldset>

      <div className="flex flex-wrap gap-4">
        <label className="flex flex-[1_1_280px] flex-col gap-1.5">
          <span className="lbl">File</span>
          <input key={format} type="file" accept={fmt.accept} className="inp py-2 text-sm"
            onChange={(e) => { setFile(e.target.files?.[0] ?? null); reset(); }} />
        </label>
        {format === "ai-learning-path" && (
          <label className="flex flex-[1_1_280px] flex-col gap-1.5">
            <span className="lbl">Progress file (optional)</span>
            <input type="file" accept=".json,application/json" className="inp py-2 text-sm"
              onChange={(e) => { setProgress(e.target.files?.[0] ?? null); reset(); }} />
            <span className="text-xs text-muted">JSON with “done” and “notes” keyed by post id. Without it, path items come in as To learn.</span>
          </label>
        )}
      </div>

      <div className="flex flex-wrap gap-2.5">
        <button className="btn" disabled={!file || busy} onClick={() => run(true)}>
          {busy && !report ? "Checking…" : "Preview import"}
        </button>
        <button className="btn btn-dark" disabled={!file || busy || !report || !report.dry_run} onClick={() => run(false)}>
          {busy && report ? "Importing…" : "Import now"}
        </button>
      </div>

      {error ? <ErrorBox error={error} /> : null}
      {report && <ReportView report={report} />}
    </section>
  );
}

function ReportView({ report }: { report: ImportReport }) {
  const s = report.summary;
  const tiles: [string, number][] = [
    ["New bookmarks", s.bookmarks_created],
    ["Already saved", s.bookmarks_matched],
    ["Existing updated", s.bookmarks_updated],
    ["Skipped rows", s.rows_skipped],
    ["New topics", s.topics_created],
    ["Topics matched", s.topics_matched],
    ["New tracks", s.groups_created],
    ["New tags", s.tags_created],
    ["Topic links added", s.links_added],
  ];
  const levelClass = { info: "pill", warn: "pill pill-to_learn", error: "pill pill-warn" } as const;
  return (
    <div className="flex flex-col gap-4 rounded-xl border border-line-strong p-4" role="status">
      <div className="flex flex-wrap items-center gap-2.5">
        <span className={`pill ${report.dry_run ? "" : "pill-learned"}`}>{report.dry_run ? "Preview · nothing changed yet" : "Imported"}</span>
        <span className="text-sm text-soft">{s.rows_total} rows read</span>
        {report.backup && <span className="font-mono text-xs text-muted">backup: {report.backup}</span>}
      </div>
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-3">
        {tiles.map(([k, v]) => (
          <div key={k} className="bg-surface px-3.5 py-3">
            <div className="lbl">{k}</div>
            <div className="mt-1 font-mono text-2xl">{v}</div>
          </div>
        ))}
      </div>
      {report.messages.length > 0 && (
        <details open={report.messages.some((m) => m.level !== "info")}>
          <summary className="cursor-pointer text-sm font-semibold">
            {report.messages.length + report.messages_truncated} notes
            {report.messages.some((m) => m.level === "error") && " · some rows were skipped"}
          </summary>
          <ul className="mt-2 max-h-72 overflow-y-auto rounded-lg border border-line">
            {report.messages.map((m, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-2.5 border-b border-line px-3 py-2 text-sm last:border-b-0">
                <span className={levelClass[m.level]}>{m.level}</span>
                <span className="font-mono text-xs text-muted">{m.ref}</span>
                <span>{m.text}</span>
              </li>
            ))}
            {report.messages_truncated > 0 && <li className="px-3 py-2 text-xs text-muted">…and {report.messages_truncated} more</li>}
          </ul>
        </details>
      )}
    </div>
  );
}

function ExportPanel() {
  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-6">
      <h2 className="text-2xl font-semibold tracking-[-0.02em]">Export</h2>
      <p className="text-sm text-soft">
        One JSON file with every bookmark, topic (with its learning order), track and tag. It holds no passwords or keys.
        Import it on another laptop with “Learnmarks export”.
      </p>
      <a href="/api/v1/export" download className="btn btn-dark self-start">Download export</a>
    </section>
  );
}

function SyncPanel() {
  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-6">
      <h2 className="text-2xl font-semibold tracking-[-0.02em]">USB sync</h2>
      <p className="text-sm text-soft">
        Pair your Pixel, start a session, then tap Sync Now on the phone. Changes travel only over the cable, and
        conflicts wait for your decision.
      </p>
      <Link to="/sync" className="btn btn-dark self-start">Open USB sync</Link>
    </section>
  );
}

const KIND_LABEL: Record<Backup["kind"], string> = {
  auto: "Daily",
  manual: "Manual",
  pre_import: "Before import",
  pre_restore: "Before restore",
};

function BackupsPanel() {
  const qc = useQueryClient();
  const toast = useToast();
  const list = useQuery({ queryKey: ["backups"], queryFn: api.backups });
  const [busy, setBusy] = useState<string | null>(null);

  async function backupNow() {
    setBusy("new");
    try {
      await api.createBackup();
      await qc.invalidateQueries({ queryKey: ["backups"] });
      toast({ text: "Backup saved" });
    } catch (e) {
      toast({ text: e instanceof ApiError ? e.message : "Backup failed" });
    } finally {
      setBusy(null);
    }
  }

  async function restore(b: Backup) {
    const when = formatDate(b.created_at, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
    if (!window.confirm(`Restore the backup from ${when}?\n\nEverything changes back to how it was then (${b.counts.bookmarks ?? "?"} bookmarks). A backup of the current state is taken first, so you can undo this.`)) return;
    setBusy(b.name);
    try {
      const r = await api.restoreBackup(b.name);
      await qc.invalidateQueries();
      toast({ text: `Restored. Current state saved as ${r.safety_backup}` });
    } catch (e) {
      toast({ text: e instanceof ApiError ? e.message : "Restore failed" });
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold tracking-[-0.02em]">Backups</h2>
          <p className="mt-1 max-w-2xl text-sm text-soft">
            A daily backup is taken while the app is running (the last 14 are kept), plus one before every import and restore.
            Files are in <code className="font-mono text-xs">learnmarks/data/backups</code>.
          </p>
        </div>
        <button className="btn" onClick={backupNow} disabled={busy !== null}>
          {busy === "new" ? "Backing up…" : "Back up now"}
        </button>
      </div>
      {list.error ? <ErrorBox error={list.error} /> : null}
      {list.data && list.data.length === 0 && <p className="text-sm text-soft">No backups yet.</p>}
      {list.data && list.data.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full min-w-[620px] border-collapse text-sm">
            <thead>
              <tr className="text-left">
                {["When", "Kind", "Bookmarks", "Topics", "Size", ""].map((h) => (
                  <th key={h} className="lbl border-b border-line px-3.5 py-2.5 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {list.data.map((b) => (
                <tr key={b.name} className="border-b border-line last:border-b-0">
                  <td className="px-3.5 py-2.5 font-mono text-[13px]">
                    {formatDate(b.created_at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                  </td>
                  <td className="px-3.5 py-2.5"><span className="pill">{KIND_LABEL[b.kind]}</span></td>
                  <td className="px-3.5 py-2.5 font-mono">{b.counts.bookmarks ?? "—"}</td>
                  <td className="px-3.5 py-2.5 font-mono">{b.counts.topics ?? "—"}</td>
                  <td className="px-3.5 py-2.5 font-mono text-muted">{(b.size_bytes / 1024).toFixed(0)} KB</td>
                  <td className="px-3.5 py-2.5 text-right">
                    <button className="btn py-1 text-[13px]" disabled={busy !== null} onClick={() => restore(b)}>
                      <Icon name="back" size={14} /> {busy === b.name ? "Restoring…" : "Restore"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
