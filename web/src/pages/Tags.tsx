import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { ApiError, api } from "../api";
import { Empty, ErrorBox, Icon, Loading, useToast } from "../components/ui";
import type { Tag } from "../types";

export default function Tags() {
  const { data, error, isLoading } = useQuery({ queryKey: ["tags"], queryFn: () => api.tags() });
  const [filter, setFilter] = useState("");
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorBox error={error} />;
  const shown = data.filter((t) => t.name.toLowerCase().includes(filter.toLowerCase().trim()));

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="lbl">Library · {data.length} tags</div>
          <h1 className="mt-2 text-[44px] font-semibold leading-none tracking-[-0.035em]">Tags</h1>
        </div>
        <label className="w-full max-w-xs">
          <span className="sr-only">Filter tags</span>
          <input className="inp" placeholder="Filter tags…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </label>
      </section>
      <p className="max-w-2xl text-sm text-soft">
        Tags are created when you add them to a bookmark. Rename them here, merge duplicates (e.g. “LLM” and “llms”), or delete ones you no longer use — deleting a tag never deletes bookmarks.
      </p>
      {data.length === 0 ? (
        <Empty title="No tags yet">Add tags such as <b>vLLM</b> or <b>embeddings</b> when you save a bookmark.</Empty>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-line bg-surface">
          {shown.map((t) => <TagRow key={t.id} tag={t} all={data} />)}
          {shown.length === 0 && <p className="px-5 py-6 text-sm text-soft">No tag matches “{filter}”.</p>}
        </div>
      )}
    </div>
  );
}

function TagRow({ tag, all }: { tag: Tag; all: Tag[] }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [mode, setMode] = useState<"view" | "rename" | "merge">("view");
  const [name, setName] = useState(tag.name);
  const [into, setInto] = useState("");

  async function run(fn: () => Promise<unknown>, done: string) {
    try {
      await fn();
      await qc.invalidateQueries();
      toast({ text: done });
      setMode("view");
    } catch (e) {
      toast({ text: e instanceof ApiError ? e.message : "Something went wrong" });
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3 last:border-b-0">
      {mode === "rename" ? (
        <form className="flex flex-1 flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); run(() => api.renameTag(tag.id, name), "Tag renamed"); }}>
          <label className="flex-1"><span className="sr-only">New name</span>
            <input className="inp py-1.5" autoFocus maxLength={60} value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <button className="btn btn-dark py-1.5" disabled={!name.trim()}>Rename</button>
          <button type="button" className="btn py-1.5" onClick={() => setMode("view")}>Cancel</button>
        </form>
      ) : mode === "merge" ? (
        <form className="flex flex-1 flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (into) run(() => api.mergeTag(tag.id, into), "Tags merged"); }}>
          <span className="text-sm">Merge <b>{tag.name}</b> into</span>
          <label><span className="sr-only">Target tag</span>
            <select className="inp w-auto py-1.5" value={into} onChange={(e) => setInto(e.target.value)}>
              <option value="">Choose a tag…</option>
              {all.filter((t) => t.id !== tag.id).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </label>
          <button className="btn btn-dark py-1.5" disabled={!into}>Merge</button>
          <button type="button" className="btn py-1.5" onClick={() => setMode("view")}>Cancel</button>
        </form>
      ) : (
        <>
          <Link to={`/bookmarks?tag=${tag.id}`} className="flex-1 font-medium hover:underline">{tag.name}</Link>
          <span className="lbl">{tag.count} bookmark{tag.count === 1 ? "" : "s"}</span>
          <div className="flex gap-1.5">
            <button className="btn py-1 text-[13px]" onClick={() => setMode("rename")}>Rename</button>
            <button className="btn py-1 text-[13px]" onClick={() => setMode("merge")}>Merge</button>
            <button className="btn btn-danger py-1 text-[13px]" aria-label={`Delete tag ${tag.name}`}
              onClick={() => window.confirm(`Delete the tag “${tag.name}”? It is removed from ${tag.count} bookmark(s).`) &&
                run(() => api.deleteTag(tag.id), "Tag deleted")}>
              <Icon name="trash" size={14} />
            </button>
          </div>
        </>
      )}
    </div>
  );
}
