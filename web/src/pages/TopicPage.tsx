import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { SortableContext, arrayMove, rectSortingStrategy, sortableKeyboardCoordinates, useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, type BookmarkQuery } from "../api";
import TopicForm from "../components/TopicForm";
import { ErrorBox, Icon, Loading, StatusPill, TopicCover, patternFor, useToast } from "../components/ui";
import { PLATFORM_LABEL, PRIORITY_LABEL, STATUSES, type Bookmark, type Status } from "../types";

const SORTS = [
  { key: "order", label: "Learning order" },
  { key: "date_saved", label: "Date saved" },
  { key: "title", label: "Title" },
  { key: "priority", label: "Priority" },
  { key: "status", label: "Status" },
];

async function fetchAll(q: BookmarkQuery): Promise<Bookmark[]> {
  const out: Bookmark[] = [];
  for (let offset = 0; ; offset += 100) {
    const page = await api.bookmarks({ ...q, limit: 100, offset });
    out.push(...page.items);
    if (out.length >= page.total || page.items.length === 0) return out;
  }
}

export default function TopicPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [filter, setFilter] = useState<Status | "all">("all");
  const [sort, setSort] = useState("order");
  const [editing, setEditing] = useState(false);

  const topic = useQuery({ queryKey: ["topic", id], queryFn: () => api.topic(id) });
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard });
  const listKey = ["topic-bookmarks", id, sort];
  const list = useQuery({ queryKey: listKey, queryFn: () => fetchAll({ topic: id, sort }) });

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  if (topic.isLoading) return <Loading />;
  if (topic.error || !topic.data) return <ErrorBox error={topic.error} />;
  const t = topic.data;
  const group = dash.data?.groups.find((g) => g.topics.some((x) => x.id === t.id));
  const number = group?.topics.find((x) => x.id === t.id)?.number ?? "";
  const all = list.data ?? [];
  const items = filter === "all" ? all : all.filter((b) => b.status === filter);
  const canDrag = sort === "order" && filter === "all";
  const c = t.counts;

  async function onDragEnd(e: DragEndEvent) {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    const from = all.findIndex((b) => b.id === active.id);
    const to = all.findIndex((b) => b.id === over.id);
    const next = arrayMove(all, from, to);
    const beforeId = next[to + 1]?.id ?? null;
    qc.setQueryData(listKey, next.map((b, i) => ({ ...b, topics: b.topics.map((r) => (r.id === id ? { ...r, position: i + 1 } : r)) })));
    try {
      await api.moveInTopic(id, String(active.id), beforeId);
    } catch {
      toast({ text: "Could not save the new order — reloaded the list." });
    }
    qc.invalidateQueries({ queryKey: ["topic-bookmarks", id] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  }

  return (
    <div className="flex flex-col gap-7">
      <section className="flex flex-wrap items-start gap-8">
        <div className="flex flex-[1_1_520px] flex-col gap-3.5">
          <div className="lbl">
            <Link to="/topics" className="text-muted hover:text-ink">{group?.name ?? "Topics"}</Link>
            {number && <> / Topic {number}</>}
          </div>
          <h1 className="font-mono text-[clamp(30px,3.6vw,42px)] font-medium leading-[1.08] tracking-[-0.04em]">{t.name}</h1>
          {t.description && <p className="max-w-[620px] text-[17px] text-soft">{t.description}</p>}
          <div className="mt-1 flex flex-wrap gap-2.5">
            <Link to={`/bookmarks/new?topic=${t.id}`} className="btn rounded-full"><Icon name="plus" /> Add to this topic</Link>
            <button className="btn rounded-full" onClick={() => setEditing((v) => !v)}><Icon name="edit" /> Edit topic</button>
          </div>
        </div>
        <div className="hidden w-[210px] shrink-0 lg:block">
          <TopicCover color={t.color} number={number || "··"} label={t.level ?? undefined} pattern={patternFor(t.id)} big />
        </div>
      </section>

      {editing && (
        <section className="rounded-2xl border border-line bg-surface p-5">
          <TopicForm
            initial={t}
            submitLabel="Save topic"
            onCancel={() => setEditing(false)}
            onSubmit={async (data) => {
              await api.updateTopic(t.id, t.version, data);
              setEditing(false);
              await qc.invalidateQueries();
            }}
          />
          <div className="mt-5 border-t border-line pt-4">
            <button
              className="btn btn-danger"
              onClick={async () => {
                if (!window.confirm(`Delete the topic “${t.name}”? Its ${c.total} bookmarks are kept; they just leave this topic.`)) return;
                await api.deleteTopic(t.id);
                await qc.invalidateQueries();
                navigate("/topics");
              }}
            >
              <Icon name="trash" /> Delete topic
            </button>
          </div>
        </section>
      )}

      <section aria-label="Progress" className="flex flex-wrap items-center gap-4.5 rounded-2xl border border-line bg-surface px-4.5 py-4">
        <div className="flex flex-[1_1_300px] gap-1" aria-hidden="true">
          {all.map((b) => (
            <span key={b.id} className="h-2.5 flex-1 rounded-[3px]"
              style={{ background: { saved: "var(--color-line-strong)", to_learn: "#e3cd78", in_progress: "var(--color-ink)", learned: "#5faf7e" }[b.status] }} />
          ))}
          {all.length === 0 && <span className="h-2.5 flex-1 rounded-[3px] bg-line" />}
        </div>
        <span className="font-mono text-[13px]">
          {c.learned} learned · {c.in_progress} in progress · {c.to_learn} to learn · {c.saved} saved
        </span>
      </section>

      <section className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Filter by status" className="flex flex-wrap gap-2">
          <button className="chip" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>All {c.total}</button>
          {STATUSES.map((s) => (
            <button key={s.key} className="chip" aria-pressed={filter === s.key} onClick={() => setFilter(s.key)}>
              {s.label} {c[s.key]}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-[13px] text-soft">
          Sort
          <select className="inp w-auto py-1.5 text-[13px]" value={sort} onChange={(e) => setSort(e.target.value)}>
            {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </label>
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div className="lbl">
            {canDrag ? "Learning order · drag ⋮⋮ to reorder" : "Reordering is available in learning order with no filter"}
          </div>
          <div className="lbl">{items.length} shown</div>
        </div>
        {list.isLoading && <Loading />}
        {list.error && <ErrorBox error={list.error} />}
        {!list.isLoading && items.length === 0 && (
          <p className="rounded-xl border border-dashed border-line-strong bg-surface/60 px-5 py-8 text-center text-sm text-soft">
            {all.length === 0 ? "No bookmarks in this topic yet." : "Nothing with this status."}
          </p>
        )}
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <SortableContext items={items.map((b) => b.id)} strategy={rectSortingStrategy}>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3">
              {items.map((b) => <Tile key={b.id} b={b} topicId={id} draggable={canDrag} />)}
            </div>
          </SortableContext>
        </DndContext>
      </section>
    </div>
  );
}

function Tile({ b, topicId, draggable }: { b: Bookmark; topicId: string; draggable: boolean }) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: b.id,
    disabled: !draggable,
  });
  const pos = b.topics.find((t) => t.id === topicId)?.position ?? 0;
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`flex items-start gap-2.5 rounded-xl border bg-surface py-3.5 pl-2.5 pr-3.5 transition-shadow ${isDragging ? "z-10 border-ink shadow-xl" : "border-line hover:border-muted hover:shadow-md"}`}
    >
      {draggable ? (
        <button
          ref={setActivatorNodeRef}
          {...attributes}
          {...listeners}
          aria-label={`Move “${b.title}”`}
          className="cursor-grab touch-none rounded p-0.5 text-muted hover:text-ink active:cursor-grabbing"
        >
          <Icon name="grip" size={18} />
        </button>
      ) : (
        <span className="w-[22px]" />
      )}
      <span className="w-6 pt-0.5 font-mono text-[13px] text-muted">{String(pos).padStart(2, "0")}</span>
      <Link to={`/bookmarks/${b.id}`} className="flex min-w-0 flex-1 flex-col gap-1.5">
        <span className="text-[15px] font-semibold leading-snug">{b.title}</span>
        <span className="font-mono text-[11.5px] text-muted">
          {b.url ? <>{b.author_handle ? `@${b.author_handle} · ` : ""}{PLATFORM_LABEL[b.source_platform]}</> : "Checklist"}
          {b.tags.length > 0 && ` · ${b.tags.slice(0, 2).map((t) => t.name).join(", ")}`}
        </span>
        <span className="flex items-center gap-1.5">
          <StatusPill status={b.status} />
          <span className="lbl text-[10px]">Priority {PRIORITY_LABEL[b.priority]}</span>
        </span>
      </Link>
    </div>
  );
}
