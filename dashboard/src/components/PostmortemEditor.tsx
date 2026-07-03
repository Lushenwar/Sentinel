"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { savePostmortem } from "@/lib/api";

export function PostmortemEditor({ incidentId, initial }: { incidentId: string; initial: string }) {
  const [text, setText] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await savePostmortem(incidentId, text);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <div>
        <textarea value={text} onChange={(e) => setText(e.target.value)} />
        <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
          <button onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
          <button className="secondary" onClick={() => { setText(initial); setEditing(false); }}>Cancel</button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <ReactMarkdown>{text}</ReactMarkdown>
      <button className="secondary" onClick={() => setEditing(true)}>Edit</button>
    </div>
  );
}
