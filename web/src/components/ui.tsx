import { createContext, useCallback, useContext, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { ApiError } from "../api";
import { STATUS_LABEL, type Status } from "../types";

export function Logo({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 26 26" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <circle cx="5" cy="13" r="2.6" />
      <circle cx="20" cy="5" r="2.6" />
      <circle cx="20" cy="13" r="2.6" />
      <circle cx="20" cy="21" r="2.6" />
      <path d="M7.5 12 17.5 6M7.6 13h9.8M7.5 14l10 6" />
    </svg>
  );
}

export function StatusPill({ status }: { status: Status }) {
  return <span className={`pill pill-${status}`}>{STATUS_LABEL[status]}</span>;
}

const ICONS = {
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  back: <path d="M15 5 8 12l7 7" />,
  external: <><path d="M14 4h6v6" /><path d="M20 4 10 14" /><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5" /></>,
  grip: <><circle cx="9" cy="6" r="1.3" /><circle cx="15" cy="6" r="1.3" /><circle cx="9" cy="12" r="1.3" /><circle cx="15" cy="12" r="1.3" /><circle cx="9" cy="18" r="1.3" /><circle cx="15" cy="18" r="1.3" /></>,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  edit: <><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="m13.5 6.5 4 4" /></>,
  trash: <><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
  moon: <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />,
  monitor: <><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></>,
  usb: <><path d="M12 3v14" /><path d="m9 6 3-3 3 3" /><path d="M8 11h0M16 9h0" /><path d="M8 11v2l4 3 4-3V9" /><circle cx="12" cy="19" r="2" /></>,
};

export function Icon({ name, size = 16, className = "" }: { name: keyof typeof ICONS; size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}>
      {ICONS[name]}
    </svg>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="lbl py-10 text-center" role="status">{label}</div>;
}

export function ErrorBox({ error }: { error: unknown }) {
  const msg = error instanceof ApiError ? error.message : error instanceof Error ? error.message : "Something went wrong";
  const offline = error instanceof TypeError;
  return (
    <div role="alert" className="rounded-xl border border-warn-line bg-warn-bg px-4 py-3 text-sm text-warn-ink">
      {offline ? "Can't reach the Learnmarks backend. Is `learnmarks serve` running?" : msg}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-line-strong bg-surface/60 px-6 py-10 text-center">
      <div className="text-lg font-semibold">{title}</div>
      {children && <div className="mt-2 text-sm text-soft">{children}</div>}
    </div>
  );
}

export function TopicCover({ color, number, label, pattern, big = false }: {
  color: string; number: string; label?: string; pattern: string; big?: boolean;
}) {
  return (
    <div className="relative pt-2.5 text-on-pastel" aria-hidden="true">
      <div className={`absolute left-0 top-0 h-3.5 w-[72px] rounded-t-md ${big ? "topic-bg brightness-90" : ""}`}
        style={big ? ({ "--topic": color } as CSSProperties) : { background: "rgba(39,39,39,.10)" }} />
      <div
        className={`${pattern} ${big ? "topic-bg" : ""} flex items-end justify-between rounded-[0_10px_10px_10px] border border-black/10 px-3.5 py-3 ${big ? "h-[170px]" : "h-[118px]"}`}
        style={big ? ({ "--topic": color } as CSSProperties) : { backgroundColor: "rgba(255,255,255,.28)" }}
      >
        <span className={`font-mono font-medium leading-none tracking-[-0.05em] ${big ? "text-[56px]" : "text-[40px]"}`}>{number}</span>
        {label && <span className="lbl text-on-pastel/80">{label}</span>}
      </div>
    </div>
  );
}

export function patternFor(id: string): string {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) | 0;
  return ["pat-dots", "pat-lines", "pat-grid", "pat-waves"][Math.abs(h) % 4];
}

export function formatDate(iso: string, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" }) {
  const d = iso.length === 10 ? new Date(`${iso}T00:00:00`) : new Date(iso);
  return d.toLocaleDateString("en-GB", opts);
}

/** Debounce a changing value. */
export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

// ---------- toasts ----------

interface Toast {
  id: number;
  text: string;
  action?: { label: string; run: () => void };
}

const ToastCtx = createContext<(t: Omit<Toast, "id">) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = next.current++;
    setToasts((all) => [...all, { ...t, id }]);
    setTimeout(() => setToasts((all) => all.filter((x) => x.id !== id)), 6000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="flex items-center gap-4 rounded-xl bg-inverse px-4 py-3 text-sm text-on-inverse shadow-lg">
            <span>{t.text}</span>
            {t.action && (
              <button className="font-semibold underline underline-offset-2"
                onClick={() => { t.action!.run(); setToasts((all) => all.filter((x) => x.id !== t.id)); }}>
                {t.action.label}
              </button>
            )}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

// ---------- theme ----------

export type ThemeChoice = "system" | "light" | "dark";
const THEME_KEY = "lm-theme";

function readTheme(): ThemeChoice {
  try {
    const t = localStorage.getItem(THEME_KEY);
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

/** Cycles System → Light → Dark. "System" follows the OS appearance setting. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<ThemeChoice>(readTheme);
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") delete root.dataset.theme;
    else root.dataset.theme = theme;
    try {
      if (theme === "system") localStorage.removeItem(THEME_KEY);
      else localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* storage unavailable: the choice just lasts for this visit */
    }
  }, [theme]);
  const next: Record<ThemeChoice, ThemeChoice> = { system: "light", light: "dark", dark: "system" };
  const label: Record<ThemeChoice, string> = { system: "System", light: "Light", dark: "Dark" };
  const icon = ({ system: "monitor", light: "sun", dark: "moon" } as const)[theme];
  return (
    <button
      type="button"
      className="btn h-10 w-10 !px-0"
      onClick={() => setTheme(next[theme])}
      aria-label={`Theme: ${label[theme]}. Switch to ${label[next[theme]]}`}
      title={`Theme: ${label[theme]}`}
    >
      <Icon name={icon} size={18} />
    </button>
  );
}
