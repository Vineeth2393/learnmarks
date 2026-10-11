import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ApiError, api, type SyncConflict } from "../api";
import { ErrorBox, Icon, StatusPill, formatDate, useToast } from "../components/ui";
import { PRIORITY_LABEL, type Status } from "../types";

const WHEN: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" };

export default function Sync() {
  return (
    <div className="flex flex-col gap-8">
      <section>
        <div className="lbl">USB sync · cable only, no cloud</div>
        <h1 className="mt-2 text-[clamp(36px,4.4vw,46px)] font-semibold leading-[1.05] tracking-[-0.035em]">
          Plug in. <span className="font-mono font-medium tracking-[-0.04em]">Sync.</span> Unplug.
        </h1>
        <p className="mt-3 max-w-xl text-soft">
          Start a session here, then tap <b>Sync Now</b> on your phone. The tunnel closes after 10 minutes.
        </p>
      </section>
      <div className="flex flex-wrap gap-5">
        <UsbCard />
        <DevicesCard />
      </div>
      <Conflicts />
      <SyncLog />
    </div>
  );
}

function UsbCard() {
  const qc = useQueryClient();
  const toast = useToast();
  const status = useQuery({ queryKey: ["usb"], queryFn: api.usbStatus, refetchInterval: 3000 });
  const [busy, setBusy] = useState(false);
  const s = status.data;
  const phone = s?.devices.find((d) => d.state === "device");

  async function toggle() {
    setBusy(true);
    try {
      const next = s?.tunnel_open ? await api.usbStop() : await api.usbStart();
      qc.setQueryData(["usb"], next);
      if (next.tunnel_open) toast({ text: "Tunnel open — now tap Sync Now on the phone" });
    } catch (e) {
      toast({ text: e instanceof ApiError ? e.message : "Couldn't talk to adb" });
    } finally {
      setBusy(false);
    }
  }

  const dot = !s?.adb_found || !phone ? "#E3CD78" : "#5FAF7E";
  return (
    <section className="flex flex-[1_1_380px] flex-col gap-4 rounded-2xl bg-inverse p-5.5 text-on-inverse shadow-xl">
      <div className="flex items-center justify-between gap-2.5">
        <span className="lbl text-inverse-muted">{phone ? `${(phone.model ?? "Phone").replace(/_/g, " ")} · ${phone.serial}` : "USB"}</span>
        <span className="pill border-inverse-line bg-transparent text-on-inverse">
          <span className="h-[7px] w-[7px] rounded-full" style={{ background: dot }} />
          {s?.tunnel_open ? "Tunnel open" : phone ? "Cable detected" : "Not connected"}
        </span>
      </div>
      <div>
        <div className="text-[22px] font-semibold">{s?.tunnel_open ? "Waiting for the phone…" : phone ? "Ready to start" : "Connect your phone"}</div>
        <div className="mt-1 font-mono text-[12.5px] text-on-inverse/80">{status.isLoading ? "Checking adb…" : s?.message}</div>
      </div>
      <div className="flex flex-wrap gap-2.5">
        <button className="btn border-on-inverse bg-on-inverse font-semibold text-inverse" disabled={busy || (!phone && !s?.tunnel_open)} onClick={toggle}>
          <Icon name="usb" /> {s?.tunnel_open ? "Stop session" : "Start USB sync session"}
        </button>
      </div>
      {s && !s.adb_found && (
        <code className="rounded-lg bg-on-inverse/10 px-3 py-2 font-mono text-xs">brew install android-platform-tools</code>
      )}
    </section>
  );
}

function DevicesCard() {
  const qc = useQueryClient();
  const toast = useToast();
  const devices = useQuery({ queryKey: ["devices"], queryFn: api.devices, refetchInterval: 5000 });
  const [code, setCode] = useState<{ code: string; expires_at: string } | null>(null);
  const [left, setLeft] = useState(0);

  useEffect(() => {
    if (!code) return;
    const tick = () => setLeft(Math.max(0, Math.round((new Date(code.expires_at).getTime() - Date.now()) / 1000)));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [code]);

  useEffect(() => {
    // A new device appeared while a code was showing: pairing worked.
    if (code && devices.data?.some((d) => new Date(d.paired_at).getTime() > Date.now() - 5 * 60_000)) {
      setCode(null);
      toast({ text: "Phone paired" });
    }
  }, [devices.data, code, toast]);

  return (
    <section className="flex flex-[1_1_380px] flex-col gap-4 rounded-2xl border border-line bg-surface p-5.5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Paired phones</h2>
          <p className="mt-1 text-sm text-soft">A phone needs a one-time code before it can sync.</p>
        </div>
        <button className="btn" onClick={async () => setCode(await api.pairingCode())}>Pair a phone</button>
      </div>
      {code && (
        <div className="rounded-xl border border-dashed border-line-strong p-4">
          {left > 0 ? (
            <>
              <div className="lbl">Pairing code · expires in {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}</div>
              <div className="mt-2 font-mono text-[34px] font-medium tracking-[0.12em]">{code.code}</div>
              <p className="mt-2 text-sm text-soft">Start the USB session, then in the app open <b>Sync → Pair with laptop</b> and type this code.</p>
            </>
          ) : (
            <p className="text-sm text-soft">The code expired. Press “Pair a phone” for a new one.</p>
          )}
        </div>
      )}
      {devices.error ? <ErrorBox error={devices.error} /> : null}
      {devices.data?.length === 0 && !code && <p className="text-sm text-soft">No phones paired yet.</p>}
      {devices.data?.map((d) => (
        <div key={d.id} className="flex flex-wrap items-center gap-3 border-t border-line pt-3">
          <div className="flex-1">
            <div className="font-semibold">{d.name}</div>
            <div className="font-mono text-xs text-muted">
              paired {formatDate(d.paired_at, WHEN)} · last sync {d.last_seen_at ? formatDate(d.last_seen_at, WHEN) : "never"}
              {d.pending_for_device > 0 && ` · ${d.pending_for_device} changes waiting`}
            </div>
          </div>
          <button className="btn btn-danger py-1 text-[13px]" onClick={async () => {
            if (!window.confirm(`Unpair ${d.name}? It will need a new code to sync again. Nothing on the phone is deleted.`)) return;
            await api.revokeDevice(d.id);
            await qc.invalidateQueries({ queryKey: ["devices"] });
          }}>Unpair</button>
        </div>
      ))}
    </section>
  );
}

function show(field: string | null, value: string | null) {
  if (value === null) return <span className="text-muted">(empty)</span>;
  if (field === "status") return <StatusPill status={value as Status} />;
  if (field === "priority") return <span className="pill">{PRIORITY_LABEL[Number(value)] ?? value}</span>;
  return <span className="whitespace-pre-line text-sm">{value}</span>;
}

function Conflicts() {
  const qc = useQueryClient();
  const toast = useToast();
  const list = useQuery({ queryKey: ["conflicts"], queryFn: api.conflicts, refetchInterval: 5000 });
  const [busy, setBusy] = useState<string | null>(null);

  async function choose(c: SyncConflict, choice: "keep_server" | "take_mobile" | "keep_both") {
    setBusy(c.id);
    try {
      await api.resolveConflict(c.id, choice);
      await qc.invalidateQueries();
      toast({ text: "Resolved. The phone picks it up on its next sync." });
    } catch (e) {
      toast({ text: e instanceof ApiError ? e.message : "Couldn't resolve" });
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="flex flex-col gap-3.5">
      <h2 className="text-2xl font-semibold tracking-[-0.02em]">Needs your decision</h2>
      {list.data?.length === 0 && (
        <p className="rounded-2xl border border-line bg-surface px-5 py-4 text-sm text-soft">No conflicts. Changes from the phone merged cleanly.</p>
      )}
      {list.data?.map((c) => {
        const what = c.kind === "edit_vs_delete" ? "Edited on the phone, deleted on the laptop"
          : c.kind === "duplicate_create" ? "Saved on both — takeaways differ"
          : `${c.field === "description" ? "Takeaway" : c.field === "status" ? "Status" : "Priority"} changed on both`;
        const suggestStatus = c.field === "status" && c.server_value && c.mobile_value
          ? (["saved", "to_learn", "in_progress", "learned"].indexOf(c.mobile_value) > ["saved", "to_learn", "in_progress", "learned"].indexOf(c.server_value) ? "phone" : "laptop")
          : null;
        return (
          <div key={c.id} className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-5.5">
            <div className="flex flex-wrap items-center justify-between gap-2.5">
              <span className="pill pill-warn">{what}</span>
              <span className="font-mono text-xs text-muted">{c.device_name} · {formatDate(c.detected_at, WHEN)}</span>
            </div>
            <Link to={`/bookmarks/${c.bookmark_id}`} className="text-xl font-semibold hover:underline">{c.bookmark_title}</Link>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
              {c.kind === "field" && (
                <div className="rounded-xl border border-dashed border-line-strong p-3.5">
                  <div className="lbl mb-2">Before (last sync)</div>{show(c.field, c.base_value)}
                </div>
              )}
              <div className="rounded-xl border border-line-strong p-3.5">
                <div className="lbl mb-2">Laptop</div>{c.kind === "edit_vs_delete" ? <span className="text-sm">Deleted</span> : show(c.field, c.server_value)}
              </div>
              <div className="rounded-xl border border-line-strong p-3.5">
                <div className="lbl mb-2">Phone</div>{show(c.field, c.mobile_value)}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2.5">
              <button className="btn btn-dark" disabled={busy === c.id} onClick={() => choose(c, "keep_server")}>
                {c.kind === "edit_vs_delete" ? "Keep it deleted" : "Keep laptop"}
              </button>
              <button className="btn" disabled={busy === c.id} onClick={() => choose(c, "take_mobile")}>
                {c.kind === "edit_vs_delete" ? "Restore with phone's change" : "Use phone"}
              </button>
              {c.field === "description" && (
                <button className="btn" disabled={busy === c.id} onClick={() => choose(c, "keep_both")}>Keep both</button>
              )}
              {suggestStatus && <span className="font-mono text-xs text-muted">Suggested: {suggestStatus} (further along). Nothing changes until you choose.</span>}
            </div>
          </div>
        );
      })}
    </section>
  );
}

function SyncLog() {
  const log = useQuery({ queryKey: ["sync-log"], queryFn: api.syncLog, refetchInterval: 5000 });
  const cls: Record<string, string> = { success: "pill-learned", failed: "pill-warn", partial: "pill-to_learn", running: "" };
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-2xl font-semibold tracking-[-0.02em]">Sync log</h2>
      {log.data?.length === 0 && <p className="text-sm text-soft">No syncs yet.</p>}
      {log.data && log.data.length > 0 && (
        <div className="overflow-x-auto rounded-2xl border border-line bg-surface">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="text-left">
                {["When", "Phone", "From phone", "To phone", "Result"].map((h) => (
                  <th key={h} className="lbl border-b border-line px-3.5 py-2.5 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {log.data.map((r) => (
                <tr key={r.id} className="border-b border-line last:border-b-0">
                  <td className="px-3.5 py-3 font-mono text-[13px]">{formatDate(r.started_at, WHEN)}</td>
                  <td className="px-3.5 py-3">{r.device_name}</td>
                  <td className="px-3.5 py-3">
                    {r.ops_received === 0 ? "—" : `${r.ops_received} changes · ${r.ops_applied} applied`}
                    {r.ops_conflicted > 0 && ` · ${r.ops_conflicted} conflict`}
                    {r.ops_rejected > 0 && ` · ${r.ops_rejected} rejected`}
                  </td>
                  <td className="px-3.5 py-3">{r.rows_sent} updates</td>
                  <td className="px-3.5 py-3"><span className={`pill ${cls[r.outcome] ?? ""}`} title={r.error ?? undefined}>{r.outcome}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
