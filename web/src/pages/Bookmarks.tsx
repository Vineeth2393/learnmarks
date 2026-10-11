import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { api, type BookmarkQuery } from "../api";
import { BookmarkRow } from "../components/cards";
import { Empty, ErrorBox, Loading } from "../components/ui";
import { PLATFORM_LABEL, PRIORITY_LABEL, STATUSES, type Platform, type Status } from "../types";

const PAGE = 50;
const SORTS = [
  { key: "", label: "Best match / newest" },
  { key: "date_saved", label: "Date saved" },
  { key: "title", label: "Title" },
  { key: "priority", label: "Priority" },
  { key: "status", label: "Status" },
  { key: "updated", label: "Recently edited" },
];

export default function Bookmarks() {
  const [params, setParams] = useSearchParams();
  const [showFilters, setShowFilters] = useState(
    ["source", "priority", "topic", "tag", "saved_from", "saved_to"].some((k) => params.has(k)),
  );

  const q: BookmarkQuery = {
    q: params.get("q") ?? undefined,
    topic: params.get("topic") ?? undefined,
    tag: params.getAll("tag"),
    tag_mode: (params.get("tag_mode") as "any" | "all") ?? undefined,
    source: params.getAll("source") as Platform[],
    status: params.getAll("status") as Status[],
    priority: params.getAll("priority").map(Number),
    saved_from: params.get("saved_from") ?? undefined,
    saved_to: params.get("saved_to") ?? undefined,
    no_topic: params.get("no_topic") === "1",
    sort: params.get("sort") ?? undefined,
    dir: (params.get("dir") as "asc" | "desc") ?? undefined,
  };
  const list = useInfiniteQuery({
    queryKey: ["bookmarks", q],
    queryFn: ({ pageParam }) => api.bookmarks({ ...q, limit: PAGE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((n, p) => n + p.items.length, 0);
      return loaded < last.total && last.items.length > 0 ? loaded : undefined;
    },
    placeholderData: keepPreviousData,
  });
  const total = list.data?.pages[0]?.total;
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];
  const topics = useQuery({ queryKey: ["topics"], queryFn: api.topics });
  const tags = useQuery({ queryKey: ["tags"], queryFn: () => api.tags() });

  function update(fn: (p: URLSearchParams) => void) {
    const next = new URLSearchParams(params);
    fn(next);
    setParams(next, { replace: true });
  }
  const toggle = (key: string, value: string) =>
    update((p) => {
      const vals = p.getAll(key);
      p.delete(key);
      (vals.includes(value) ? vals.filter((v) => v !== value) : [...vals, value]).forEach((v) => p.append(key, v));
    });
  const set = (key: string, value: string | null) => update((p) => (value ? p.set(key, value) : p.delete(key)));
  const active = (key: string, value: string) => params.getAll(key).includes(value);

  // Mirrors the backend default: best match and A→Z run ascending, everything else newest/highest first.
  const effectiveSort = q.sort || (q.q ? "relevance" : "date_saved");
  const dir = q.dir ?? (effectiveSort === "relevance" || effectiveSort === "title" ? "asc" : "desc");
  const heading = q.no_topic ? "Without a topic" : q.q ? `Results for “${q.q}”` : "All bookmarks";
  const filterCount = ["source", "priority", "topic", "tag", "saved_from", "saved_to"].reduce((n, k) => n + params.getAll(k).length, 0);

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="lbl">Library{total !== undefined ? ` · ${total} found` : ""}</div>
          <h1 className="mt-2 text-[40px] font-semibold leading-none tracking-[-0.035em]">{heading}</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <label className="flex items-center gap-2 text-[13px] text-soft">
            Sort
            <select className="inp w-auto py-1.5 text-[13px]" value={params.get("sort") ?? ""}
              onChange={(e) => set("sort", e.target.value || null)}>
              {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </label>
          <button className="btn py-1.5" onClick={() => set("dir", dir === "asc" ? "desc" : "asc")}
            aria-label="Reverse sort direction">
            {dir === "asc" ? "↑ Asc" : "↓ Desc"}
          </button>
          <button className="btn py-1.5" aria-expanded={showFilters} onClick={() => setShowFilters((v) => !v)}>
            Filters{filterCount ? ` · ${filterCount}` : ""}
          </button>
        </div>
      </section>

      <div role="group" aria-label="Filter by status" className="flex flex-wrap gap-2">
        {STATUSES.map((s) => (
          <button key={s.key} className="chip" aria-pressed={active("status", s.key)} onClick={() => toggle("status", s.key)}>
            {s.label}
          </button>
        ))}
        {(params.toString() && params.toString() !== `q=${encodeURIComponent(q.q ?? "")}`) ? (
          <button className="chip border-dashed" onClick={() => update((p) => { for (const k of [...p.keys()]) if (k !== "q") p.delete(k); })}>
            Clear filters
          </button>
        ) : null}
      </div>

      {showFilters && (
        <section className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-5 rounded-2xl border border-line bg-surface p-5">
          <fieldset className="flex flex-col gap-2">
            <legend className="lbl mb-2">Source</legend>
            <div className="flex flex-wrap gap-2">
              {(Object.keys(PLATFORM_LABEL) as Platform[]).map((p) => (
                <button key={p} className="chip" aria-pressed={active("source", p)} onClick={() => toggle("source", p)}>{PLATFORM_LABEL[p]}</button>
              ))}
            </div>
          </fieldset>
          <fieldset className="flex flex-col gap-2">
            <legend className="lbl mb-2">Priority</legend>
            <div className="flex flex-wrap gap-2">
              {[3, 2, 1].map((p) => (
                <button key={p} className="chip" aria-pressed={active("priority", String(p))} onClick={() => toggle("priority", String(p))}>
                  {PRIORITY_LABEL[p]}
                </button>
              ))}
            </div>
          </fieldset>
          <label className="flex flex-col gap-2">
            <span className="lbl">Topic</span>
            <select className="inp" value={params.get("topic") ?? ""} onChange={(e) => set("topic", e.target.value || null)}>
              <option value="">Any topic</option>
              {topics.data?.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.counts.total})</option>)}
            </select>
          </label>
          <fieldset className="flex flex-col gap-2">
            <legend className="lbl mb-2">Saved between</legend>
            <div className="flex gap-2">
              <label className="flex-1"><span className="sr-only">From</span>
                <input type="date" className="inp py-1.5" value={params.get("saved_from") ?? ""} onChange={(e) => set("saved_from", e.target.value || null)} />
              </label>
              <label className="flex-1"><span className="sr-only">To</span>
                <input type="date" className="inp py-1.5" value={params.get("saved_to") ?? ""} onChange={(e) => set("saved_to", e.target.value || null)} />
              </label>
            </div>
          </fieldset>
          <fieldset className="col-span-full flex flex-col gap-2">
            <legend className="lbl mb-2 flex items-center gap-3">
              Tags
              <span className="seg inline-flex text-[11px] normal-case tracking-normal">
                <button type="button" aria-pressed={q.tag_mode !== "all"} className="!min-h-0 !px-2.5 !py-1 !text-xs" onClick={() => set("tag_mode", null)}>Any</button>
                <button type="button" aria-pressed={q.tag_mode === "all"} className="!min-h-0 !px-2.5 !py-1 !text-xs" onClick={() => set("tag_mode", "all")}>All</button>
              </span>
            </legend>
            <div className="flex max-h-40 flex-wrap gap-2 overflow-y-auto">
              {tags.data?.length === 0 && <span className="text-sm text-soft">No tags yet.</span>}
              {tags.data?.map((t) => (
                <button key={t.id} className="chip" aria-pressed={active("tag", t.id)} onClick={() => toggle("tag", t.id)}>
                  {t.name} <span className="font-mono text-[11px] opacity-70">{t.count}</span>
                </button>
              ))}
            </div>
          </fieldset>
        </section>
      )}

      {list.isLoading && <Loading />}
      {list.error && <ErrorBox error={list.error} />}
      {total === 0 && (
        <Empty title="Nothing found">{q.q ? "Try fewer or shorter words — every word must match." : "No bookmarks match these filters."}</Empty>
      )}
      {items.length > 0 && (
        <div className={`border-t border-line ${list.isFetching && !list.isFetchingNextPage ? "opacity-70" : ""}`}>
          {items.map((b) => <BookmarkRow key={b.id} b={b} />)}
        </div>
      )}
      {list.hasNextPage && total !== undefined && (
        <button className="btn self-center" onClick={() => list.fetchNextPage()} disabled={list.isFetchingNextPage}>
          {list.isFetchingNextPage ? "Loading…" : `Show more (${total - items.length} left)`}
        </button>
      )}
    </div>
  );
}
