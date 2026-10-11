import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { ApiError, api } from "../api";
import { TopicCard } from "../components/cards";
import TopicForm from "../components/TopicForm";
import { ErrorBox, Icon, Loading, useToast } from "../components/ui";

export default function Topics() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard });
  const groups = useQuery({ queryKey: ["groups"], queryFn: api.groups });
  const [creating, setCreating] = useState(false);
  const [groupName, setGroupName] = useState("");

  const addGroup = useMutation({
    mutationFn: (name: string) => api.createGroup(name),
    onSuccess: () => {
      setGroupName("");
      qc.invalidateQueries({ queryKey: ["groups"] });
    },
    onError: (e) => toast({ text: e instanceof ApiError ? e.message : "Could not add the track" }),
  });

  if (dash.isLoading) return <Loading />;
  if (dash.error || !dash.data) return <ErrorBox error={dash.error} />;
  const emptyGroups = (groups.data ?? []).filter((g) => !dash.data.groups.some((dg) => dg.id === g.id));

  return (
    <div className="flex flex-col gap-10">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="lbl">Library · {dash.data.topic_count} topics</div>
          <h1 className="mt-2 text-[44px] font-semibold leading-none tracking-[-0.035em]">Topics</h1>
        </div>
        {!creating && (
          <button className="btn btn-dark" onClick={() => setCreating(true)}>
            <Icon name="plus" /> New topic
          </button>
        )}
      </section>

      {creating && (
        <section className="rounded-2xl border border-line bg-surface p-5">
          <h2 className="mb-4 text-lg font-semibold">New topic</h2>
          <TopicForm
            submitLabel="Create topic"
            onCancel={() => setCreating(false)}
            onSubmit={async (data) => {
              const t = await api.createTopic(data);
              await qc.invalidateQueries();
              navigate(`/topics/${t.id}`);
            }}
          />
        </section>
      )}

      {dash.data.groups.map((g) => (
        <section key={g.id ?? "none"} className="flex flex-col gap-4">
          <div>
            <div className="lbl">Track · {g.topics.length} topics · {g.bookmark_count} bookmarks</div>
            <h2 className="mt-1.5 text-[26px] font-semibold tracking-[-0.02em]">{g.name}</h2>
          </div>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(250px,1fr))] gap-4.5">
            {g.topics.map((t) => <TopicCard key={t.id} t={t} groupName={g.name} />)}
          </div>
        </section>
      ))}

      <section className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-5">
        <h2 className="text-lg font-semibold">Tracks</h2>
        <p className="text-sm text-soft">Tracks group topics, e.g. “AI Engineering path” and “Supporting skills”.</p>
        {emptyGroups.length > 0 && (
          <p className="text-sm text-soft">Empty: {emptyGroups.map((g) => g.name).join(", ")}</p>
        )}
        <form className="flex flex-wrap gap-2.5" onSubmit={(e) => { e.preventDefault(); if (groupName.trim()) addGroup.mutate(groupName.trim()); }}>
          <label className="flex-[1_1_260px]">
            <span className="sr-only">Track name</span>
            <input className="inp" maxLength={80} placeholder="New track name" value={groupName}
              onChange={(e) => setGroupName(e.target.value)} />
          </label>
          <button className="btn" disabled={!groupName.trim() || addGroup.isPending}>Add track</button>
        </form>
      </section>
    </div>
  );
}
