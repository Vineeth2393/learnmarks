import type {
  Bookmark,
  BookmarkList,
  CheckUrl,
  Dashboard,
  Group,
  Level,
  Platform,
  Status,
  Tag,
  Topic,
} from "./types";

/** An RFC 9457 problem returned by the backend. */
export class ApiError extends Error {
  status: number;
  body: Record<string, unknown>;

  constructor(status: number, body: Record<string, unknown>) {
    super(String(body.detail ?? body.title ?? `Request failed (${status})`));
    this.status = status;
    this.body = body;
  }
}

type Params = Record<string, string | number | boolean | undefined | null | (string | number)[]>;

function qs(params?: Params): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)));
    else sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

async function request<T>(
  method: string,
  path: string,
  opts: { json?: unknown; params?: Params; version?: number } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (opts.json !== undefined) headers["Content-Type"] = "application/json";
  if (opts.version !== undefined) headers["If-Match"] = String(opts.version);
  const res = await fetch(`/api/v1${path}${qs(opts.params)}`, {
    method,
    headers,
    body: opts.json !== undefined ? JSON.stringify(opts.json) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body);
  return body as T;
}

export interface BookmarkQuery {
  q?: string;
  topic?: string;
  tag?: string[];
  tag_mode?: "any" | "all";
  source?: Platform[];
  status?: Status[];
  priority?: number[];
  saved_from?: string;
  saved_to?: string;
  no_topic?: boolean;
  sort?: string;
  dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export interface BookmarkInput {
  url?: string;
  title?: string | null;
  date_saved?: string;
  description?: string | null;
  status?: Status;
  priority?: number;
  source_platform?: Platform;
  topic_ids?: string[];
  tag_names?: string[];
}

export interface TopicInput {
  name?: string;
  description?: string | null;
  color?: string;
  group_id?: string | null;
  level?: Level | null;
}

export type ImportFormat = "ai-learning-path" | "learnmarks" | "csv";

export interface ImportReport {
  format: ImportFormat;
  dry_run: boolean;
  summary: {
    rows_total: number;
    rows_skipped: number;
    groups_created: number;
    topics_created: number;
    topics_matched: number;
    tags_created: number;
    bookmarks_created: number;
    bookmarks_matched: number;
    bookmarks_updated: number;
    links_added: number;
  };
  messages: { level: "info" | "warn" | "error"; ref: string; text: string }[];
  messages_truncated: number;
  backup: string | null;
}

export interface Backup {
  name: string;
  kind: "auto" | "manual" | "pre_import" | "pre_restore";
  created_at: string;
  size_bytes: number;
  counts: Record<string, number>;
}

export interface UsbStatus {
  adb_found: boolean;
  devices: { serial: string; state: string; model: string | null }[];
  tunnel_open: boolean;
  message: string;
}

export interface SyncDevice {
  id: string;
  name: string;
  paired_at: string;
  last_seen_at: string | null;
  acked_seq: number;
  pending_for_device: number;
}

export interface SyncConflict {
  id: string;
  bookmark_id: string;
  bookmark_title: string;
  kind: "field" | "edit_vs_delete" | "duplicate_create";
  field: string | null;
  base_value: string | null;
  mobile_value: string | null;
  server_value: string | null;
  detected_at: string;
  device_name: string;
}

export interface SyncLogRow {
  id: string;
  device_name: string;
  started_at: string;
  finished_at: string | null;
  outcome: string;
  ops_received: number;
  ops_applied: number;
  ops_conflicted: number;
  ops_rejected: number;
  rows_sent: number;
  error: string | null;
}

async function sendFile<T>(path: string, body: string): Promise<T> {
  const res = await fetch(`/api/v1${path}`, { method: "POST", headers: { "Content-Type": "text/plain" }, body });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, json);
  return json as T;
}

export const api = {
  dashboard: () => request<Dashboard>("GET", "/dashboard"),

  bookmarks: (q: BookmarkQuery) => request<BookmarkList>("GET", "/bookmarks", { params: q as Params }),
  bookmark: (id: string) => request<Bookmark>("GET", `/bookmarks/${id}`),
  checkUrl: (url: string) => request<CheckUrl>("GET", "/bookmarks/check-url", { params: { url } }),
  createBookmark: (data: BookmarkInput) => request<Bookmark>("POST", "/bookmarks", { json: data }),
  updateBookmark: (id: string, version: number, data: BookmarkInput) =>
    request<Bookmark>("PATCH", `/bookmarks/${id}`, { json: data, version }),
  deleteBookmark: (id: string) => request<void>("DELETE", `/bookmarks/${id}`),
  restoreBookmark: (id: string) => request<Bookmark>("POST", `/bookmarks/${id}/restore`),
  bulk: (data: Record<string, unknown>) => request<{ updated: number }>("POST", "/bookmarks/bulk", { json: data }),

  topics: () => request<Topic[]>("GET", "/topics"),
  topic: (id: string) => request<Topic>("GET", `/topics/${id}`),
  createTopic: (data: TopicInput) => request<Topic>("POST", "/topics", { json: data }),
  updateTopic: (id: string, version: number, data: TopicInput) =>
    request<Topic>("PATCH", `/topics/${id}`, { json: data, version }),
  deleteTopic: (id: string) => request<void>("DELETE", `/topics/${id}`),
  moveInTopic: (topicId: string, bookmarkId: string, beforeId: string | null) =>
    request<void>("POST", `/topics/${topicId}/move`, { json: { bookmark_id: bookmarkId, before_id: beforeId } }),

  groups: () => request<Group[]>("GET", "/topic-groups"),
  createGroup: (name: string) => request<Group>("POST", "/topic-groups", { json: { name } }),
  updateGroup: (id: string, version: number, data: { name?: string; sort_order?: number }) =>
    request<Group>("PATCH", `/topic-groups/${id}`, { json: data, version }),
  deleteGroup: (id: string) => request<void>("DELETE", `/topic-groups/${id}`),

  tags: (q?: string) => request<Tag[]>("GET", "/tags", { params: { q } }),
  renameTag: (id: string, name: string) => request<Tag>("PATCH", `/tags/${id}`, { json: { name } }),
  deleteTag: (id: string) => request<void>("DELETE", `/tags/${id}`),
  mergeTag: (id: string, intoId: string) => request<Tag>("POST", `/tags/${id}/merge`, { json: { into_id: intoId } }),

  importFile: (format: ImportFormat, body: string, dryRun: boolean) =>
    sendFile<ImportReport>(`/import?format=${format}&dry_run=${dryRun}`, body),
  usbStatus: () => request<UsbStatus>("GET", "/sync/usb"),
  usbStart: () => request<UsbStatus>("POST", "/sync/usb/start"),
  usbStop: () => request<UsbStatus>("POST", "/sync/usb/stop"),
  pairingCode: () => request<{ code: string; expires_at: string }>("POST", "/sync/pairing-codes"),
  devices: () => request<SyncDevice[]>("GET", "/sync/devices"),
  revokeDevice: (id: string) => request<void>("DELETE", `/sync/devices/${id}`),
  conflicts: () => request<SyncConflict[]>("GET", "/sync/conflicts"),
  resolveConflict: (id: string, choice: "keep_server" | "take_mobile" | "keep_both") =>
    request<void>("POST", `/sync/conflicts/${id}/resolve`, { json: { choice } }),
  syncLog: () => request<SyncLogRow[]>("GET", "/sync/log"),
  backups: () => request<Backup[]>("GET", "/backups"),
  createBackup: () => request<Backup>("POST", "/backups"),
  restoreBackup: (name: string) =>
    request<{ restored: string; safety_backup: string }>("POST", `/backups/${encodeURIComponent(name)}/restore`),
};
