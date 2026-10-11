// Mirrors backend/learnmarks/schemas.py

export type Status = "saved" | "to_learn" | "in_progress" | "learned";
export type Platform = "x" | "linkedin" | "other";
export type Level = "beginner" | "intermediate" | "advanced" | "any";

export interface TopicRef {
  id: string;
  name: string;
  color: string;
  position: number;
}

export interface TagRef {
  id: string;
  name: string;
}

export interface Bookmark {
  id: string;
  url: string;
  canonical_url: string;
  title: string;
  source_platform: Platform;
  author_handle: string | null;
  date_saved: string;
  description: string | null;
  status: Status;
  status_changed_at: string;
  priority: number;
  created_at: string;
  updated_at: string;
  version: number;
  deleted: boolean;
  topics: TopicRef[];
  tags: TagRef[];
}

export interface BookmarkList {
  items: Bookmark[];
  total: number;
}

export interface StatusCounts {
  saved: number;
  to_learn: number;
  in_progress: number;
  learned: number;
  total: number;
}

export interface Topic {
  id: string;
  name: string;
  description: string | null;
  color: string;
  group_id: string | null;
  sort_order: number;
  level: Level | null;
  version: number;
  counts: StatusCounts;
}

export interface Group {
  id: string;
  name: string;
  sort_order: number;
  version: number;
}

export interface Tag {
  id: string;
  name: string;
  count: number;
  version: number;
}

export interface CheckUrl {
  canonical_url: string;
  source_platform: Platform;
  author_handle: string | null;
  suggested_title: string;
  existing_id: string | null;
  existing_title: string | null;
}

export interface DashTopic {
  id: string;
  name: string;
  color: string;
  level: Level | null;
  number: string;
  counts: StatusCounts;
  preview: string[];
}

export interface DashGroup {
  id: string | null;
  name: string;
  topics: DashTopic[];
  bookmark_count: number;
}

export interface Dashboard {
  counts: StatusCounts;
  by_source: Record<Platform, number>;
  topic_count: number;
  groups: DashGroup[];
  continue_item: {
    bookmark: Bookmark;
    topic_name: string | null;
    topic_number: string | null;
    position: number | null;
    topic_total: number | null;
  } | null;
  recent: Bookmark[];
  needs_review: number;
}

export const STATUSES: { key: Status; label: string }[] = [
  { key: "saved", label: "Saved" },
  { key: "to_learn", label: "To learn" },
  { key: "in_progress", label: "In progress" },
  { key: "learned", label: "Learned" },
];

export const STATUS_LABEL: Record<Status, string> = {
  saved: "Saved",
  to_learn: "To learn",
  in_progress: "In progress",
  learned: "Learned",
};

export const PRIORITY_LABEL: Record<number, string> = { 1: "Low", 2: "Medium", 3: "High" };

export const PLATFORM_LABEL: Record<Platform, string> = { x: "X", linkedin: "LinkedIn", other: "Other" };

export const PALETTE: { name: string; hex: string }[] = [
  { name: "Sage", hex: "#C9CDBB" },
  { name: "Rose", hex: "#E9C9C3" },
  { name: "Mustard", hex: "#EFD98A" },
  { name: "Slate", hex: "#BCC6D6" },
  { name: "Lavender", hex: "#D5C6E6" },
  { name: "Teal", hex: "#A9CCC9" },
  { name: "Sand", hex: "#E6D3B8" },
  { name: "Grey", hex: "#D9D9DC" },
];

export const PATTERNS = ["pat-dots", "pat-lines", "pat-grid", "pat-waves"];
