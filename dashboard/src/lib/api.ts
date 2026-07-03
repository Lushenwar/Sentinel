const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type SuspectCommit = {
  commit_hash: string;
  author: string;
  timestamp: string;
  rationale: string;
  confidence_score: number;
};

export type MatchedRunbook = {
  id: string;
  title: string;
  similarity_score: number;
  primary_action: string;
};

export type Diagnostics = {
  suspect_commits: SuspectCommit[];
  matched_runbooks: MatchedRunbook[];
  impact_assessment: { error_rate_delta_pct: number | null; estimated_affected_users: number | null };
};

export type Trigger = {
  source: string;
  alert_name: string;
  timestamp: string;
  error_signature: string;
};

// shape returned by core's db rows (see core/db.py)
export type Incident = {
  id: string;
  status: "triggered" | "triaging" | "resolving" | "resolved";
  trigger_data: Trigger;
  diagnostics: Diagnostics | null;
  postmortem: string | null;
  created_at: string;
  updated_at: string;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

export const listIncidents = () => api<Incident[]>("/incidents");
export const getIncident = (id: string) => api<Incident>(`/incidents/${id}`);
export const resolveIncident = (id: string) =>
  api<Incident>(`/incidents/${id}/resolve`, { method: "POST" });
export const savePostmortem = (id: string, postmortem: string) =>
  api<Incident>(`/incidents/${id}/postmortem`, {
    method: "PATCH",
    body: JSON.stringify({ postmortem }),
  });
export const getCommitDiff = (id: string, hash: string) =>
  api<{ commit_hash: string; diff: string }>(`/incidents/${id}/commits/${hash}/diff`);
