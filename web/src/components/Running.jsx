import { useEffect, useState } from "react";
import { Check, Clock } from "./Icons.jsx";

const STEPS = [
  { at: 0.0, label: "Reading the scripts" },
  { at: 0.05, label: "Finding hooks and cliffhangers in each episode" },
  { at: 0.72, label: "Building multi-episode trailers" },
  { at: 0.82, label: "Checking timestamps and lengths" },
  { at: 0.9, label: "Ranking what to post first" },
];

const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

export default function Running({ progress, message }) {
  const [start] = useState(() => Date.now());
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const elapsed = (now - start) / 1000;
  const current = STEPS.reduce((i, s, idx) => (progress >= s.at ? idx : i), 0);
  const busy = /busy|timed out|switching|rate limit/i.test(message || "");

  return (
    <div className="card running" role="status" aria-live="polite">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div>
          <h2>Finding your promos…</h2>
          <div className="muted">Each AI request usually takes 10–60 seconds. You can keep this tab open and come back.</div>
        </div>
        <span className="pill"><Clock size={16} /> {mmss(elapsed)}</span>
      </div>
      <div className="progress"><div style={{ width: `${Math.max(3, Math.round(progress * 100))}%` }} /></div>
      <ul className="steps-list">
        {STEPS.map((s, i) => (
          <li key={s.label} className={i < current ? "done" : i === current ? "active" : ""}>
            <span className="sdot">{i < current && <Check size={14} />}</span>
            <span>
              {s.label}
              {i === current && message && (
                <div style={{ fontWeight: 400, fontSize: 13, color: busy ? "var(--yellow-ink)" : "var(--muted)" }}>{message}</div>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
