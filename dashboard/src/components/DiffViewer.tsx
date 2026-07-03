"use client";

import { useState } from "react";
import { getCommitDiff } from "@/lib/api";

function lineClass(line: string): string {
  if (line.startsWith("+") && !line.startsWith("+++")) return "diff-line diff-add";
  if (line.startsWith("-") && !line.startsWith("---")) return "diff-line diff-del";
  if (line.startsWith("@@") || line.startsWith("diff ") || line.startsWith("index ")) return "diff-line diff-meta";
  return "diff-line";
}

export function DiffViewer({ incidentId, commitHash }: { incidentId: string; commitHash: string }) {
  const [diff, setDiff] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (!open && diff === null) {
      try {
        const res = await getCommitDiff(incidentId, commitHash);
        setDiff(res.diff);
      } catch (e) {
        setError((e as Error).message);
      }
    }
    setOpen(!open);
  }

  return (
    <div>
      <button className="secondary" onClick={toggle}>
        {open ? "Hide diff" : "View diff"}
      </button>
      {open && error && <p className="error-sig">{error}</p>}
      {open && diff && (
        <div style={{ marginTop: 8, overflowX: "auto" }}>
          {diff.split("\n").map((line, i) => (
            <div key={i} className={lineClass(line)}>{line || " "}</div>
          ))}
        </div>
      )}
    </div>
  );
}
