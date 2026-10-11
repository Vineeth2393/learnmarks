import type { CSSProperties } from "react";
import { Link } from "react-router";
import type { Bookmark, DashTopic } from "../types";
import { PLATFORM_LABEL } from "../types";
import { StatusPill, TopicCover, formatDate, patternFor } from "./ui";

export function BookmarkRow({ b, showTopic = true }: { b: Bookmark; showTopic?: boolean }) {
  const topic = b.topics[0];
  return (
    <Link
      to={`/bookmarks/${b.id}`}
      className="flex flex-wrap items-center gap-3.5 border-b border-line px-2 py-3.5 hover:bg-surface"
    >
      <span className="lbl w-16 shrink-0">{formatDate(b.date_saved)}</span>
      <span className="min-w-0 flex-[1_1_260px]">
        <span className="block text-[15px] font-semibold leading-snug">{b.title}</span>
        <span className="font-mono text-xs text-muted">
          {b.author_handle ? `@${b.author_handle}` : b.url ? PLATFORM_LABEL[b.source_platform] : "Checklist"}
          {showTopic && topic && <> · <span style={{ boxShadow: `inset 0 -3px 0 ${topic.color}` }}>{topic.name}</span></>}
          {b.tags.length > 0 && <> · {b.tags.slice(0, 3).map((t) => `#${t.name}`).join(" ")}</>}
        </span>
      </span>
      {b.priority === 3 && <span className="lbl text-[10px]">High</span>}
      <StatusPill status={b.status} />
    </Link>
  );
}

export function TopicCard({ t, groupName }: { t: DashTopic; groupName?: string }) {
  const pct = t.counts.total ? Math.round((t.counts.learned / t.counts.total) * 100) : 0;
  return (
    <Link
      to={`/topics/${t.id}`}
      className="card-lift topic-bg flex min-h-[320px] flex-col gap-3.5 rounded-2xl p-4"
      style={{ "--topic": t.color } as CSSProperties}
      aria-label={`${t.name}${groupName ? `, ${groupName}` : ""}`}
    >
      <TopicCover color={t.color} number={t.number} label={t.level ?? undefined} pattern={patternFor(t.id)} />
      <div className="text-xl font-semibold leading-tight tracking-[-0.015em]">{t.name}</div>
      <div className="flex flex-col gap-1.5 text-[13.5px] text-on-pastel/85">
        {t.preview.length === 0 && <span className="text-on-pastel/70">No bookmarks yet</span>}
        {t.preview.map((p, i) => (
          <div key={i} className="flex gap-2">
            <span className="font-mono">+</span>
            <span>{p}</span>
          </div>
        ))}
      </div>
      <div className="mt-auto flex flex-col gap-2.5">
        <div className="h-1 overflow-hidden rounded-full bg-black/10">
          <div className="h-full bg-on-pastel" style={{ width: `${pct}%` }} />
        </div>
        <div className="flex items-center justify-between">
          <span className="pill border-black/15 bg-white/55 text-on-pastel">{t.counts.total} saved · {t.counts.learned} learned</span>
          <span className="text-sm">Open →</span>
        </div>
      </div>
    </Link>
  );
}
