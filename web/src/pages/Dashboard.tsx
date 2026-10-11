import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "../api";
import { BookmarkRow, TopicCard } from "../components/cards";
import { Empty, ErrorBox, Loading, StatusPill } from "../components/ui";

export default function Dashboard() {
  const { data, error, isLoading } = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard });
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorBox error={error} />;

  const c = data.counts;
  const today = new Date().toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
  const stats = [
    ["Total", c.total],
    ["Saved", c.saved],
    ["To learn", c.to_learn],
    ["In progress", c.in_progress],
    ["Learned", c.learned],
    ["X · LinkedIn", `${data.by_source.x} · ${data.by_source.linkedin}`],
  ] as const;
  const cont = data.continue_item;

  return (
    <div className="flex flex-col gap-10">
      <section className="flex flex-wrap items-end justify-between gap-7">
        <div className="flex-[1_1_520px]">
          <div className="lbl">Dashboard · {today}</div>
          <h1 className="mt-3 text-[clamp(40px,5vw,58px)] font-semibold leading-[1.02] tracking-[-0.035em]">
            Everything you saved,
            <br />
            <span className="font-mono font-medium tracking-[-0.04em]">in order.</span>
          </h1>
          <p className="mt-3.5 max-w-[560px] text-[17px] text-soft">
            {c.total === 0
              ? "Nothing saved yet. Paste a link from X or LinkedIn to start."
              : `${c.total} bookmarks across ${data.topic_count} topics. Pick up where you left off, or open a topic and follow its learning order.`}
          </p>
        </div>
        {cont && (
          <Link
            to={`/bookmarks/${cont.bookmark.id}`}
            className="card-lift flex flex-[0_1_420px] flex-col gap-3 rounded-2xl bg-inverse px-5 py-5 text-on-inverse shadow-xl"
          >
            <div className="flex items-center justify-between">
              <span className="lbl text-inverse-muted">Continue{cont.topic_number ? ` · Topic ${cont.topic_number}` : ""}</span>
              <span className="pill pill-in_progress border-inverse-line">In progress</span>
            </div>
            <div className="text-[21px] font-semibold tracking-[-0.01em]">{cont.bookmark.title}</div>
            <div className="flex items-center gap-3">
              {cont.position && cont.topic_total ? (
                <>
                  <div className="flex gap-[3px]" aria-hidden="true">
                    {Array.from({ length: Math.min(cont.topic_total, 24) }, (_, i) => (
                      <span key={i} className="h-4 w-1.5 rounded-sm"
                        style={{ background: i + 1 < cont.position! ? "var(--color-on-inverse)" : i + 1 === cont.position ? "#A9CCC9" : "var(--color-inverse-track)" }} />
                    ))}
                  </div>
                  <span className="font-mono text-[13px] text-on-inverse/85">
                    {String(cont.position).padStart(2, "0")} / {String(cont.topic_total).padStart(2, "0")}
                  </span>
                </>
              ) : (
                <span className="font-mono text-[13px] text-on-inverse/85">{cont.topic_name ?? "No topic"}</span>
              )}
              <span className="ml-auto text-sm">Open →</span>
            </div>
          </Link>
        )}
      </section>

      <section aria-label="Totals"
        className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-3 xl:grid-cols-6">
        {stats.map(([k, v]) => (
          <div key={k} className="bg-surface px-4.5 py-4">
            <div className="lbl">{k}</div>
            <div className="mt-1.5 font-mono text-3xl font-medium tracking-[-0.03em]">{v}</div>
          </div>
        ))}
      </section>

      {data.groups.length === 0 && (
        <Empty title="No topics yet">
          <Link to="/topics" className="underline">Create your first topic</Link> to organise bookmarks into a learning order.
        </Empty>
      )}

      {data.groups.map((g) => (
        <section key={g.id ?? "none"} className="flex flex-col gap-4">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <div>
              <div className="lbl">Track · {g.topics.length} topics · {g.bookmark_count} bookmarks</div>
              <h2 className="mt-1.5 text-[28px] font-semibold tracking-[-0.02em]">{g.name}</h2>
            </div>
            <Link to="/topics" className="lbl text-ink">All topics →</Link>
          </div>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(250px,1fr))] gap-4.5">
            {g.topics.map((t) => <TopicCard key={t.id} t={t} groupName={g.name} />)}
          </div>
        </section>
      ))}

      <section className="flex flex-wrap gap-7">
        <div className="min-w-0 flex-[2_1_520px]">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[22px] font-semibold tracking-[-0.015em]">Recently saved</h2>
            <Link to="/bookmarks" className="lbl text-ink">All bookmarks →</Link>
          </div>
          <div className="mt-3 border-t border-line">
            {data.recent.length === 0 && <p className="py-6 text-sm text-soft">Nothing yet.</p>}
            {data.recent.map((b) => <BookmarkRow key={b.id} b={b} />)}
          </div>
        </div>
        <div className="flex flex-[1_1_300px] flex-col gap-3.5">
          <h2 className="text-[22px] font-semibold tracking-[-0.015em]">Needs attention</h2>
          {data.needs_review > 0 ? (
            <Link to="/bookmarks?no_topic=1" className="flex flex-col gap-1.5 rounded-2xl border border-line bg-surface px-4.5 py-4">
              <span className="lbl">Needs review · {data.needs_review}</span>
              <span className="text-[15px] font-semibold">Bookmarks without a topic, or tagged needs-review</span>
              <span className="mt-1 text-sm">Review →</span>
            </Link>
          ) : (
            <div className="rounded-2xl border border-line bg-surface px-4.5 py-4 text-sm text-soft">All caught up.</div>
          )}
          {c.in_progress > 1 && (
            <Link to="/bookmarks?status=in_progress" className="flex flex-col gap-1.5 rounded-2xl border border-line bg-surface px-4.5 py-4">
              <span className="lbl">In progress · {c.in_progress}</span>
              <span className="flex items-center gap-2 text-[15px] font-semibold">Several things at once <StatusPill status="in_progress" /></span>
              <span className="mt-1 text-sm">See them →</span>
            </Link>
          )}
        </div>
      </section>
    </div>
  );
}
