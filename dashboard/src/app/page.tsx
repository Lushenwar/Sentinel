"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listIncidents, type Incident } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function IncidentFeed() {
  const [incidents, setIncidents] = useState<Incident[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = () =>
      listIncidents()
        .then((data) => !cancelled && (setIncidents(data), setError(null)))
        .catch((e) => !cancelled && setError(e.message));
    poll();
    const id = setInterval(poll, 3000); // ponytail: plain polling, swap for SSE if latency matters
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  if (error) return <p className="error-sig">Cannot reach core API: {error}</p>;
  if (!incidents) return <p>Loading…</p>;
  if (incidents.length === 0) return <p>No incidents yet. Trigger one with chaos_cli.</p>;

  return (
    <table>
      <thead>
        <tr><th>Incident</th><th>Alert</th><th>Status</th><th>Triggered</th></tr>
      </thead>
      <tbody>
        {incidents.map((inc) => (
          <tr key={inc.id}>
            <td><Link href={`/incidents/${inc.id}`}>{inc.id}</Link></td>
            <td>{inc.trigger_data.alert_name}</td>
            <td><StatusBadge status={inc.status} /></td>
            <td>{new Date(inc.trigger_data.timestamp).toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
