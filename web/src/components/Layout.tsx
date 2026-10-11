import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation, useNavigate, useSearchParams } from "react-router";
import { api } from "../api";
import { Icon, Logo, ThemeToggle } from "./ui";

export default function Layout() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <div className="flex flex-1 flex-wrap">
        <Sidebar />
        <main className="min-w-0 flex-[999_1_560px] px-5 pb-16 pt-8 sm:px-10">
          <div className="mx-auto max-w-[1180px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}

function Header() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const location = useLocation();
  const [q, setQ] = useState(location.pathname === "/bookmarks" ? params.get("q") ?? "" : "");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (location.pathname !== "/bookmarks") setQ("");
  }, [location.pathname]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      const typing = el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable;
      if (e.key === "/" && !typing) {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <header className="flex flex-wrap items-center gap-4 border-b border-line bg-canvas px-6 py-3.5">
      <Link to="/" className="flex items-center gap-2.5" aria-label="Learnmarks home">
        <Logo />
        <span className="font-mono text-base font-semibold tracking-tight">learnmarks</span>
        <span className="lbl rounded bg-inverse px-1.5 py-0.5 text-[9.5px] text-on-inverse">LOCAL</span>
      </Link>
      <form
        role="search"
        className="flex flex-[1_1_320px] justify-center"
        onSubmit={(e) => {
          e.preventDefault();
          const next = new URLSearchParams(location.pathname === "/bookmarks" ? params : undefined);
          if (q.trim()) next.set("q", q.trim());
          else next.delete("q");
          navigate(`/bookmarks?${next.toString()}`);
        }}
      >
        <label className="flex w-full max-w-[520px] items-center gap-2.5 rounded-full border border-line-strong bg-surface px-4 py-2">
          <Icon name="search" className="text-muted" />
          <span className="sr-only">Search bookmarks</span>
          <input
            ref={input}
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search titles, takeaways, topics, tags…"
            className="w-full bg-transparent text-sm outline-none"
          />
          <kbd className="lbl rounded border border-line-strong px-1.5">/</kbd>
        </label>
      </form>
      <ThemeToggle />
      <Link to="/bookmarks/new" className="btn btn-dark">
        <Icon name="plus" /> Add bookmark
      </Link>
    </header>
  );
}

function Sidebar() {
  const { data } = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard });
  const { data: tags } = useQuery({ queryKey: ["tags"], queryFn: () => api.tags() });
  const { data: conflicts } = useQuery({ queryKey: ["conflicts"], queryFn: api.conflicts, refetchInterval: 30_000 });
  const c = data?.counts;
  const pct = c && c.total ? Math.round((c.learned / c.total) * 100) : 0;

  const sections = [
    {
      label: "Learn",
      items: [
        { to: "/", name: "Dashboard", end: true },
        { to: "/topics", name: "Topics", badge: data?.topic_count },
        { to: "/bookmarks?status=in_progress", name: "In progress", badge: c?.in_progress },
      ],
    },
    {
      label: "Library",
      items: [
        { to: "/bookmarks", name: "All bookmarks", badge: c?.total, end: true },
        { to: "/tags", name: "Tags", badge: tags?.length },
        { to: "/bookmarks?no_topic=1", name: "Without a topic" },
      ],
    },
    {
      label: "System",
      items: [
        { to: "/sync", name: "USB sync", badge: conflicts?.length || undefined },
        { to: "/settings", name: "Import · Backup" },
      ],
    },
  ];

  return (
    <nav aria-label="Main" className="hidden max-w-[260px] flex-[1_1_220px] flex-col gap-5 border-r border-line px-3.5 py-5 md:flex">
      {sections.map((s) => (
        <div key={s.label} className="flex flex-col gap-0.5">
          <div className="lbl px-2.5 pb-1.5">{s.label}</div>
          {s.items.map((it) => (
            <SideLink key={it.to} {...it} />
          ))}
        </div>
      ))}
      {c && (
        <div className="mt-auto border-t border-line px-2.5 pt-3">
          <div className="lbl">{c.learned} / {c.total} learned</div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-line">
            <div className="h-full bg-inverse" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}
    </nav>
  );
}

function SideLink({ to, name, badge, end }: { to: string; name: string; badge?: number; end?: boolean }) {
  const loc = useLocation();
  const [path, query] = to.split("?");
  const active =
    query !== undefined
      ? loc.pathname === path && loc.search === `?${query}`
      : end
        ? loc.pathname === path && !/(status|no_topic)=/.test(loc.search)
        : loc.pathname.startsWith(path);
  return (
    <Link
      to={to}
      aria-current={active ? "page" : undefined}
      className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm ${active ? "bg-active font-semibold text-ink" : "text-sub hover:bg-hover"}`}
    >
      <span className="flex-1">{name}</span>
      {badge !== undefined && <span className="lbl text-[10px]">{badge}</span>}
    </Link>
  );
}
