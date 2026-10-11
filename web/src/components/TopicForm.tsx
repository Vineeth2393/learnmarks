import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, type TopicInput } from "../api";
import { PALETTE, type Level, type Topic } from "../types";

const LEVELS: (Level | "")[] = ["", "beginner", "intermediate", "advanced", "any"];

export default function TopicForm({ initial, onSubmit, onCancel, submitLabel }: {
  initial?: Topic;
  onSubmit: (data: TopicInput) => Promise<unknown>;
  onCancel?: () => void;
  submitLabel: string;
}) {
  const { data: groups = [] } = useQuery({ queryKey: ["groups"], queryFn: api.groups });
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [color, setColor] = useState(initial?.color ?? PALETTE[0].hex);
  const [groupId, setGroupId] = useState(initial?.group_id ?? "");
  const [level, setLevel] = useState<Level | "">(initial?.level ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          await onSubmit({ name: name.trim(), description: description.trim() || null, color,
                           group_id: groupId || null, level: level || null });
        } catch (err) {
          setError(err instanceof ApiError ? err.message : "Could not save the topic");
        } finally {
          setBusy(false);
        }
      }}
    >
      <div className="flex flex-wrap gap-4">
        <label className="flex flex-[2_1_240px] flex-col gap-1.5">
          <span className="lbl">Name</span>
          <input className="inp" required maxLength={80} value={name} onChange={(e) => setName(e.target.value)}
            placeholder="e.g. RAG: retrieval-augmented generation" />
        </label>
        <label className="flex flex-[1_1_180px] flex-col gap-1.5">
          <span className="lbl">Track</span>
          <select className="inp" value={groupId} onChange={(e) => setGroupId(e.target.value)}>
            <option value="">No track</option>
            {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
        </label>
        <label className="flex flex-[1_1_150px] flex-col gap-1.5">
          <span className="lbl">Level</span>
          <select className="inp" value={level} onChange={(e) => setLevel(e.target.value as Level | "")}>
            {LEVELS.map((l) => <option key={l} value={l}>{l ? l[0].toUpperCase() + l.slice(1) : "Not set"}</option>)}
          </select>
        </label>
      </div>
      <label className="flex flex-col gap-1.5">
        <span className="lbl">Why this topic (optional)</span>
        <textarea className="inp" rows={2} maxLength={2000} value={description}
          onChange={(e) => setDescription(e.target.value)} />
      </label>
      <fieldset className="flex flex-col gap-1.5">
        <legend className="lbl mb-1.5">Colour</legend>
        <div className="flex flex-wrap gap-2">
          {PALETTE.map((p) => (
            <button key={p.hex} type="button" aria-pressed={color.toUpperCase() === p.hex} aria-label={p.name}
              onClick={() => setColor(p.hex)}
              className="h-9 w-9 rounded-lg border border-black/15 aria-pressed:ring-2 aria-pressed:ring-ink aria-pressed:ring-offset-2"
              style={{ background: p.hex }} />
          ))}
        </div>
      </fieldset>
      {error && <p role="alert" className="text-sm text-warn-ink">{error}</p>}
      <div className="flex gap-2.5">
        <button className="btn btn-dark" disabled={busy || !name.trim()}>{submitLabel}</button>
        {onCancel && <button type="button" className="btn" onClick={onCancel}>Cancel</button>}
      </div>
    </form>
  );
}
