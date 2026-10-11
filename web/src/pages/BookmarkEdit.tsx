import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type KeyboardEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { ApiError, api, type BookmarkInput } from "../api";
import { ErrorBox, Icon, Loading, StatusPill, formatDate, useDebounced, useToast } from "../components/ui";
import { PLATFORM_LABEL, PRIORITY_LABEL, STATUSES, type Bookmark, type Platform, type Status } from "../types";

export default function BookmarkEditPage() {
  const { id } = useParams();
  const query = useQuery({ queryKey: ["bookmark", id], queryFn: () => api.bookmark(id!), enabled: !!id });
  if (!id) return <BookmarkForm key="new" />;
  if (query.isLoading) return <Loading />;
  if (query.error || !query.data) return <ErrorBox error={query.error} />;
  return <BookmarkForm key={`${query.data.id}:${query.data.version}`} existing={query.data} />;
}

function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function BookmarkForm({ existing }: { existing?: Bookmark }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const [params] = useSearchParams();
  const topicsQ = useQuery({ queryKey: ["topics"], queryFn: api.topics });
  const tagsQ = useQuery({ queryKey: ["tags"], queryFn: () => api.tags() });

  const [url, setUrl] = useState(existing?.url ?? "");
  const [title, setTitle] = useState(existing?.title ?? "");
  const [dateSaved, setDateSaved] = useState(existing?.date_saved ?? today());
  const [source, setSource] = useState<Platform | "">(existing?.source_platform ?? "");
  const [status, setStatus] = useState<Status>(existing?.status ?? "saved");
  const [priority, setPriority] = useState(existing?.priority ?? 2);
  const [topicIds, setTopicIds] = useState<string[]>(existing?.topics.map((t) => t.id) ?? (params.get("topic") ? [params.get("topic")!] : []));
  const [tagNames, setTagNames] = useState<string[]>(existing?.tags.map((t) => t.name) ?? []);
  const [tagDraft, setTagDraft] = useState("");
  const [description, setDescription] = useState(existing?.description ?? "");
  const [error, setError] = useState<{ text: string; existingId?: string; stale?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  const debouncedUrl = useDebounced(url.trim(), 300);
  const check = useQuery({
    queryKey: ["check-url", debouncedUrl],
    queryFn: () => api.checkUrl(debouncedUrl),
    enabled: debouncedUrl.length > 3 && debouncedUrl !== existing?.url,
    retry: false,
  });
  const dup = check.data?.existing_id && check.data.existing_id !== existing?.id ? check.data : null;

  const topics = topicsQ.data ?? [];
  const selectedTopics = topicIds.map((tid) => topics.find((t) => t.id === tid)).filter((t) => !!t);
  const positions = Object.fromEntries((existing?.topics ?? []).map((t) => [t.id, t.position]));

  function addTag(raw: string) {
    const names = raw.split(",").map((s) => s.trim().replace(/\s+/g, " ")).filter(Boolean);
    setTagNames((cur) => {
      const next = [...cur];
      for (const n of names) if (!next.some((x) => x.toLowerCase() === n.toLowerCase())) next.push(n.slice(0, 60));
      return next;
    });
    setTagDraft("");
  }
  function onTagKey(e: KeyboardEvent<HTMLInputElement>) {
    if ((e.key === "Enter" || e.key === ",") && tagDraft.trim()) {
      e.preventDefault();
      addTag(tagDraft);
    } else if (e.key === "Backspace" && !tagDraft && tagNames.length) {
      setTagNames((cur) => cur.slice(0, -1));
    }
  }

  async function save() {
    setBusy(true);
    setError(null);
    const tags = tagDraft.trim() ? [...tagNames, tagDraft.trim()] : tagNames;
    try {
      let saved: Bookmark;
      if (!existing) {
        const body: BookmarkInput = {
          url: url.trim(), title: title.trim() || null, date_saved: dateSaved, description: description.trim() || null,
          status, priority, topic_ids: topicIds, tag_names: tags, ...(source ? { source_platform: source } : {}),
        };
        saved = await api.createBookmark(body);
        toast({ text: "Bookmark saved" });
      } else {
        const body: BookmarkInput = {};
        if (url.trim() !== existing.url) body.url = url.trim();
        if (title.trim() && title.trim() !== existing.title) body.title = title.trim();
        if (dateSaved !== existing.date_saved) body.date_saved = dateSaved;
        if (source && source !== existing.source_platform) body.source_platform = source;
        if (status !== existing.status) body.status = status;
        if (priority !== existing.priority) body.priority = priority;
        if ((description.trim() || null) !== existing.description) body.description = description.trim() || null;
        if (topicIds.join() !== existing.topics.map((t) => t.id).join()) body.topic_ids = topicIds;
        if (tags.join() !== existing.tags.map((t) => t.name).join()) body.tag_names = tags;
        if (Object.keys(body).length === 0) {
          toast({ text: "No changes to save" });
          setBusy(false);
          return;
        }
        saved = await api.updateBookmark(existing.id, existing.version, body);
        toast({ text: "Changes saved" });
      }
      qc.setQueryData(["bookmark", saved.id], saved);
      await qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "bookmark" });
      if (!existing) navigate(`/bookmarks/${saved.id}`, { replace: true });
    } catch (e) {
      if (e instanceof ApiError) {
        setError({
          text: e.message,
          existingId: (e.body.existing_id as string) ?? undefined,
          stale: e.status === 412,
        });
      } else setError({ text: "Could not reach the backend." });
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!existing) return;
    await api.deleteBookmark(existing.id);
    await qc.invalidateQueries();
    toast({
      text: `Deleted “${existing.title}”`,
      action: {
        label: "Undo",
        run: async () => {
          await api.restoreBookmark(existing.id);
          await qc.invalidateQueries();
        },
      },
    });
    navigate(-1);
  }

  const dirtyHint = existing ? `Version ${existing.version} · updated ${formatDate(existing.updated_at)}` : "New bookmark";

  return (
    <div className="flex flex-col gap-6">
      <div className="lbl">
        <Link to="/bookmarks" className="text-muted hover:text-ink">Bookmarks</Link>
        {existing?.topics[0] && <> / <Link to={`/topics/${existing.topics[0].id}`} className="text-muted hover:text-ink">{existing.topics[0].name}</Link></>}
        {" / "}{existing ? "Edit" : "New"}
      </div>

      {existing?.deleted && (
        <div role="status" className="flex flex-wrap items-center gap-3 rounded-xl border border-warn-line bg-warn-bg px-4 py-3 text-sm text-warn-ink">
          This bookmark is deleted.
          <button className="btn py-1" onClick={async () => {
            try {
              await api.restoreBookmark(existing.id);
              await qc.invalidateQueries();
            } catch (e) {
              setError({ text: e instanceof ApiError ? e.message : "Could not restore", existingId: e instanceof ApiError ? (e.body.existing_id as string) : undefined });
            }
          }}>Restore</button>
        </div>
      )}

      <div className="flex flex-wrap items-start gap-9">
        {existing && (
          <article className="flex min-w-0 flex-[1_1_360px] flex-col gap-4">
            <div className="flex -rotate-[0.6deg] flex-col gap-4 rounded-2xl border border-line bg-surface px-7 py-7 shadow-[0_1px_0_var(--color-line),0_18px_40px_rgba(0,0,0,.06)]">
              <div className="flex items-center justify-between gap-3">
                <span className="lbl">{existing.url ? `Reading note · ${PLATFORM_LABEL[existing.source_platform]} post` : "Checklist item"}
                  {existing.topics[0] && ` · ${String(existing.topics[0].position).padStart(2, "0")}`}</span>
                <StatusPill status={existing.status} />
              </div>
              <h1 className="text-[32px] font-semibold leading-[1.1] tracking-[-0.025em]">{existing.title}</h1>
              <div className="font-mono text-[13px] text-soft">
                {existing.author_handle && `@${existing.author_handle} · `}saved {formatDate(existing.date_saved, { day: "numeric", month: "short", year: "numeric" })}
              </div>
              <div className="whitespace-pre-line border-t border-dashed border-line-strong pt-4 text-[17px] leading-relaxed text-sub">
                {existing.description || <span className="text-muted">{existing.url ? "No takeaway yet. Why did you save this?" : "No notes yet."}</span>}
              </div>
              {existing.url && (
                <a href={existing.url} target="_blank" rel="noopener noreferrer" className="btn btn-dark self-start rounded-full">
                  Open on {PLATFORM_LABEL[existing.source_platform]} <Icon name="external" size={14} />
                </a>
              )}
            </div>
            <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line">
              {[
                ["Version", `v${existing.version}`],
                ["Duplicate key", existing.canonical_url],
                ["Created", formatDate(existing.created_at, { day: "numeric", month: "short", year: "numeric" })],
                ["Updated", formatDate(existing.updated_at, { day: "numeric", month: "short", year: "numeric" })],
              ].map(([k, v]) => (
                <div key={k} className="min-w-0 bg-surface px-3.5 py-3">
                  <dt className="lbl">{k}</dt>
                  <dd className="mt-1 truncate font-mono text-[13px]" title={v}>{v}</dd>
                </div>
              ))}
            </dl>
          </article>
        )}

        <form className="flex min-w-0 flex-[1.3_1_460px] flex-col gap-5" onSubmit={(e) => { e.preventDefault(); save(); }}>
          {!existing && <h1 className="text-[36px] font-semibold leading-none tracking-[-0.03em]">Add a bookmark</h1>}

          <label className="flex flex-col gap-1.5">
            <span className="lbl">URL (optional)</span>
            <input className="inp font-mono text-[13.5px]" autoFocus={!existing} value={url}
              onChange={(e) => setUrl(e.target.value)} placeholder="Paste a link from X or LinkedIn — or leave empty for a checklist item" />
            {check.data && !dup && debouncedUrl !== existing?.url && (
              <span className="font-mono text-xs text-done-ink">✓ {check.data.canonical_url} · not saved yet</span>
            )}
            {dup && (
              <span className="font-mono text-xs text-warn-ink">
                Already saved as “{dup.existing_title}” · <Link className="underline" to={`/bookmarks/${dup.existing_id}`}>open it</Link>
              </span>
            )}
            {check.error && <span className="font-mono text-xs text-warn-ink">{(check.error as Error).message}</span>}
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="lbl">Title</span>
            <input className="inp" maxLength={300} value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder={check.data?.suggested_title ?? "What is this post about?"} />
          </label>

          <div className="flex flex-wrap gap-4">
            <label className="flex flex-[1_1_180px] flex-col gap-1.5">
              <span className="lbl">Date saved</span>
              <input type="date" className="inp" value={dateSaved} onChange={(e) => setDateSaved(e.target.value)} required />
            </label>
            <label className="flex flex-[1_1_180px] flex-col gap-1.5">
              <span className="lbl">Source</span>
              <select className="inp" value={source} onChange={(e) => setSource(e.target.value as Platform | "")}>
                {!existing && <option value="">Detect from URL{check.data ? ` (${PLATFORM_LABEL[check.data.source_platform]})` : ""}</option>}
                {(Object.keys(PLATFORM_LABEL) as Platform[]).map((p) => <option key={p} value={p}>{PLATFORM_LABEL[p]}</option>)}
              </select>
            </label>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="lbl" id="status-label">Learning status</span>
            <div className="seg" role="group" aria-labelledby="status-label">
              {STATUSES.map((s) => (
                <button key={s.key} type="button" aria-pressed={status === s.key} onClick={() => setStatus(s.key)}>{s.label}</button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="lbl" id="prio-label">Priority</span>
            <div className="seg max-w-[360px]" role="group" aria-labelledby="prio-label">
              {[1, 2, 3].map((p) => (
                <button key={p} type="button" aria-pressed={priority === p} onClick={() => setPriority(p)}>{PRIORITY_LABEL[p]}</button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="lbl">Topics · position in learning order</span>
            <div className="flex flex-wrap items-center gap-2">
              {selectedTopics.map((t) => (
                <span key={t.id} className="inline-flex items-center gap-2 rounded-full border border-line-strong bg-surface py-1 pl-3 pr-1 text-[13px]">
                  <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: t.color }} />
                  {t.name}
                  {positions[t.id] ? <span className="font-mono text-[11px] text-muted">#{String(positions[t.id]).padStart(2, "0")}</span> : null}
                  <button type="button" aria-label={`Remove topic ${t.name}`} className="h-6 w-6 rounded-full bg-hover leading-none"
                    onClick={() => setTopicIds((ids) => ids.filter((x) => x !== t.id))}>×</button>
                </span>
              ))}
              <label>
                <span className="sr-only">Add topic</span>
                <select className="inp w-auto rounded-full py-1.5 text-[13px]" value=""
                  onChange={(e) => e.target.value && setTopicIds((ids) => [...ids, e.target.value])}>
                  <option value="">+ Add topic</option>
                  {topics.filter((t) => !topicIds.includes(t.id)).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </label>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="lbl" htmlFor="tag-input">Tags</label>
            <div className="flex flex-wrap items-center gap-2">
              {tagNames.map((n) => (
                <span key={n} className="inline-flex items-center gap-2 rounded-full border border-line-strong bg-surface py-1 pl-3 pr-1 text-[13px]">
                  {n}
                  <button type="button" aria-label={`Remove tag ${n}`} className="h-6 w-6 rounded-full bg-hover leading-none"
                    onClick={() => setTagNames((cur) => cur.filter((x) => x !== n))}>×</button>
                </span>
              ))}
              <input id="tag-input" className="inp w-44 rounded-full py-1.5 text-[13px]" list="tag-options" value={tagDraft}
                placeholder="Add tag, press Enter" onChange={(e) => setTagDraft(e.target.value)} onKeyDown={onTagKey}
                onBlur={() => tagDraft.trim() && addTag(tagDraft)} />
              <datalist id="tag-options">
                {tagsQ.data?.filter((t) => !tagNames.some((n) => n.toLowerCase() === t.name.toLowerCase())).map((t) => <option key={t.id} value={t.name} />)}
              </datalist>
            </div>
          </div>

          <label className="flex flex-col gap-1.5">
            <span className="lbl">Takeaway</span>
            <textarea className="inp resize-y" rows={3} maxLength={2000} value={description}
              onChange={(e) => setDescription(e.target.value)} placeholder="What will you learn from it?" />
          </label>

          {error && (
            <div role="alert" className="rounded-xl border border-warn-line bg-warn-bg px-4 py-3 text-sm text-warn-ink">
              {error.text}{" "}
              {error.existingId && <Link className="underline" to={`/bookmarks/${error.existingId}`}>Open the saved one</Link>}
              {error.stale && <button type="button" className="underline" onClick={() => qc.invalidateQueries({ queryKey: ["bookmark", existing?.id] })}>Reload it</button>}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4.5">
            {existing && !existing.deleted && (
              <button type="button" className="btn btn-danger" onClick={remove}><Icon name="trash" /> Delete</button>
            )}
            <span className="flex-1 text-right font-mono text-xs text-muted">{dirtyHint}</span>
            <button className="btn btn-dark" disabled={busy || !!dup || existing?.deleted || (!url.trim() && !title.trim())}>
              {busy ? "Saving…" : existing ? "Save changes" : "Save bookmark"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
