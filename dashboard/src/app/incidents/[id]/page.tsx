"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { getIncident, resolveIncident, type Incident } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { DiffViewer } from "@/components/DiffViewer";
import { PostmortemEditor } from "@/components/PostmortemEditor";

export default function IncidentDetail() {
  const { id } = useParams<{ id: string }>();
  const [incident, setIncident] = useState<Incident | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const poll = () =>
      getIncident(id)
        .then((data) => !cancelled && (setIncident(data), setError(null)))
        .catch((e) => !cancelled && setError(e.message));
    poll();
    const timer = setInterval(poll, 3000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [id]);

  if (error) return <p className="error-sig">Cannot reach core API: {error}</p>;
  if (!incident) return <p>Loading…</p>;

  const { trigger_data: trigger, diagnostics, status, postmortem } = incident;

  async function handleResolve() {
    setResolving(true);
    try {
      await resolveIncident(id);
    } finally {
      setResolving(false);
    }
  }

  return (
    <div>
      <p><Link href="/">← All incidents</Link></p>
      <h1 style={{ fontSize: 18 }}>{incident.id} <StatusBadge status={status} /></h1>

      <div className="panel">
        <h2>Trigger</h2>
        <p>{trigger.alert_name} — {trigger.source} — {new Date(trigger.timestamp).toLocaleString()}</p>
        <pre className="error-sig">{trigger.error_signature}</pre>
      </div>

      {diagnostics && (
        <div className="panel">
          <h2>Suspect commits</h2>
          {diagnostics.suspect_commits.length === 0 && <p>None found in the alert window.</p>}
          {diagnostics.suspect_commits.map((c) => (
            <div key={c.commit_hash} style={{ marginBottom: 12 }}>
              <p>
                <strong>{c.commit_hash}</strong> — {c.author} — {Math.round(c.confidence_score * 100)}% confidence
              </p>
              <p style={{ color: "var(--muted)" }}>{c.rationale}</p>
              <DiffViewer incidentId={id} commitHash={c.commit_hash} />
            </div>
          ))}
        </div>
      )}

      {diagnostics && diagnostics.matched_runbooks.length > 0 && (
        <div className="panel">
          <h2>Matched runbooks</h2>
          {diagnostics.matched_runbooks.map((r) => (
            <p key={r.id}>
              <strong>{r.title}</strong> ({Math.round(r.similarity_score * 100)}% match) — {r.primary_action}
            </p>
          ))}
        </div>
      )}

      <div className="panel">
        <h2>Postmortem</h2>
        {postmortem ? (
          <PostmortemEditor incidentId={id} initial={postmortem} />
        ) : status === "resolved" || status === "resolving" ? (
          <p>Generating…</p>
        ) : (
          <button onClick={handleResolve} disabled={resolving}>
            {resolving ? "Resolving…" : "Resolve & generate postmortem"}
          </button>
        )}
      </div>
    </div>
  );
}
