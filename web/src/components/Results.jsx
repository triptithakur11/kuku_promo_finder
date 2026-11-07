import { useEffect, useMemo, useState } from "react";
import { csvFor, download, decide, exportEdit, downloadBlob } from "../api.js";
import PromoCard from "./PromoCard.jsx";
import { Film, Layers, Alert, UserCheck, Search, Download, Sparkle, X } from "./Icons.jsx";

const TABS = [
  { id: "all", label: "All", test: () => true },
  { id: "multi", label: "Multi-episode", test: (p) => p.kind === "montage" },
  { id: "check", label: "Needs a look", test: (p) => p.flags.length > 0 },
  { id: "approved", label: "Approved", test: (p, d) => d[p.id]?.status === "approved" },
  { id: "rejected", label: "Rejected", test: (p, d) => d[p.id]?.status === "rejected" },
];

export default function Results({ result }) {
  const [decisions, setDecisions] = useState(result.decisions || {});
  const [tab, setTab] = useState("all");
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(20);
  const [fps, setFps] = useState(30);
  const [pattern, setPattern] = useState("episode-{ep:03d}.mp4");
  const [err, setErr] = useState("");

  useEffect(() => {
    setDecisions(result.decisions || {}); setTab("all"); setQ(""); setLimit(20);
    // one-time migration of approvals that older versions kept only in this browser
    try {
      const key = `approved:${result.out_dir}:${result.created}`;
      const old = JSON.parse(localStorage.getItem(key) || "{}");
      if (result.slug && Object.keys(result.decisions || {}).length === 0) {
        Object.entries(old).filter(([, v]) => v).forEach(([id]) => onDecide(id, "approved"));
      }
      localStorage.removeItem(key);
    } catch {}
  }, [result]);

  async function onDecide(id, status, reason = "") {
    setErr("");
    const prev = decisions;
    setDecisions((d) => {
      const n = { ...d };
      if (status) n[id] = { status, reason }; else delete n[id];
      return n;
    });
    if (!result.slug) return;
    try { setDecisions(await decide(result.slug, id, status, reason)); }
    catch (e) { setDecisions(prev); setErr(`Couldn't save that decision: ${e.message}`); }
  }

  const approved = useMemo(() => result.promos.filter((p) => decisions[p.id]?.status === "approved"), [result, decisions]);
  const rejected = result.promos.filter((p) => decisions[p.id]?.status === "rejected");
  const reasons = Object.entries(rejected.reduce((m, p) => {
    const r = decisions[p.id].reason || "No reason"; m[r] = (m[r] || 0) + 1; return m;
  }, {})).sort((a, b) => b[1] - a[1]);
  const top10 = result.promos.slice(0, 10).filter((p) => decisions[p.id]);
  const top10ok = top10.filter((p) => decisions[p.id].status === "approved").length;

  const test = TABS.find((t) => t.id === tab).test;
  const needle = q.trim().toLowerCase();
  const list = result.promos.filter((p) => test(p, decisions) &&
    (!needle || [p.title, p.hook, p.cliffhanger, p.why, ...p.episodes.map((e) => `ep ${e} episode ${e}`)].join(" ").toLowerCase().includes(needle)));
  const shown = list.slice(0, limit);
  const rulesOnly = result.model === "rules-only";
  const slug = result.show.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 40);
  const covered = new Set(result.promos.flatMap((p) => p.episodes)).size;

  return (
    <>
      <section className="row-section" style={{ paddingTop: 32 }}>
        <div className="row-label">
          <h3>Summary</h3>
          <p>{rulesOnly ? "These picks come from keyword rules only." : `Picked by ${result.model}, then checked and ranked in code.`}</p>
        </div>
        <div>
          <div className="grid-4">
            <div className="card stat"><span className="icon-tile sm"><Film size={20} /></span><div><b>{result.counts.kept}</b><span>promos found</span></div></div>
            <div className="card stat"><span className="icon-tile sm green"><Sparkle size={20} /></span><div><b>{covered}/{result.episodes_processed.length}</b><span>episodes covered</span></div></div>
            <div className="card stat"><span className="icon-tile sm"><Layers size={20} /></span><div><b>{result.promos.filter((p) => p.kind === "montage").length}</b><span>multi-episode trailers</span></div></div>
            <div className="card stat"><span className="icon-tile sm orange"><Alert size={20} /></span><div><b>{result.promos.filter((p) => p.flags.length).length}</b><span>need a look</span></div></div>
          </div>
          {rulesOnly && (
            <div className="banner"><Alert size={18} />
              <span>Rules only: fast and free, but it doesn't understand the story. Run again with an AI model for better picks and a written reason for each one.</span>
            </div>
          )}
        </div>
      </section>

      <section className="row-section">
        <div className="row-label">
          <div style={{ position: "sticky", top: 96 }}>
            <h3>Promos</h3>
            <p>Ranked by what to post first. Approve the ones to post and reject the rest with a reason. Your decisions are saved with this run and used to measure how good the picks are.</p>

            <div className="card" style={{ padding: 16, marginTop: 18 }}>
              <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                <span className="icon-tile sm green"><UserCheck size={20} /></span>
                <div style={{ lineHeight: 1.35 }}>
                  <div><b style={{ fontSize: 18 }}>{approved.length}</b> <span className="muted">approved · </span><b style={{ fontSize: 18 }}>{rejected.length}</b> <span className="muted">rejected</span></div>
                  {top10.length > 0 && <div className="muted" style={{ fontSize: 13 }}>Top 10: {top10ok} of {top10.length} reviewed are good</div>}
                </div>
              </div>
              {reasons.length > 0 && (
                <div className="chips" style={{ marginTop: 10 }}>
                  {reasons.slice(0, 3).map(([r, n]) => <span key={r} className="pill sm orange"><X size={12} /> {r} · {n}</span>)}
                </div>
              )}
              <button className="btn btn-primary" style={{ width: "100%", marginTop: 14 }} disabled={!approved.length}
                onClick={async () => {
                  try { downloadBlob(`${slug}-edit-export.zip`, await exportEdit(approved, fps, pattern)); }
                  catch (e) { setErr(e.message); }
                }}>
                <Download size={18} /> Export for editing (EDL + cut script)
              </button>
              <button className="btn" style={{ width: "100%", marginTop: 8 }} disabled={!approved.length}
                onClick={async () => download(`${slug}-approved.csv`, await csvFor(approved), "text/csv")}>
                Approved as CSV
              </button>
              <details className="mini-settings">
                <summary>Export settings</summary>
                <div className="field" style={{ marginTop: 10 }}>
                  <label htmlFor="fps">Frame rate</label>
                  <select id="fps" className="input" value={fps} onChange={(e) => setFps(+e.target.value)}>
                    {[24, 25, 30, 50, 60].map((f) => <option key={f} value={f}>{f} fps</option>)}
                  </select>
                </div>
                <div className="field" style={{ marginTop: 10 }}>
                  <label htmlFor="pattern">Episode video file names</label>
                  <input id="pattern" className="input" value={pattern} onChange={(e) => setPattern(e.target.value)} />
                  <div className="hint">{"{ep:03d}"} becomes 001, 002… → {safeFormat(pattern)}</div>
                </div>
              </details>
              <div className="hint" style={{ fontSize: 12, color: "var(--muted)", marginTop: 10 }}>
                The EDL imports into Premiere Pro and DaVinci Resolve. cut_promos.sh cuts the clips with ffmpeg once you have the episode videos.
              </div>
              {err && <div className="error" style={{ marginTop: 10 }}><Alert size={16} /> {err}</div>}
            </div>
            <button className="btn" style={{ width: "100%", marginTop: 10 }}
              onClick={() => download(`${slug}-all-promos.json`, JSON.stringify(result, null, 2), "application/json")}>
              Download all results · JSON
            </button>
          </div>
        </div>

        <div className="card">
          <div className="toolbar">
            <b>{list.length} promo{list.length === 1 ? "" : "s"}</b>
            <span className="grow" />
            <div className="segmented" role="tablist">
              {TABS.map((t) => (
                <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? "on" : ""} onClick={() => { setTab(t.id); setLimit(20); }}>
                  {t.label}<span className="n">{result.promos.filter((p) => t.test(p, decisions)).length}</span>
                </button>
              ))}
            </div>
            <div className="search">
              <Search size={18} />
              <input className="input" placeholder="Search hooks, lines, episodes…" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
          </div>

          <div className="list-body">
            {shown.length === 0 && (
              <div className="empty-state">
                <span className="icon-tile gray"><Search size={22} /></span>
                {tab === "approved" ? "Nothing approved yet. Press Approve on the promos you want to post."
                  : tab === "rejected" ? "Nothing rejected yet." : "No promos match."}
              </div>
            )}
            {shown.map((p, i) => (
              <div key={p.id}>
                {tab === "all" && !needle && i === 0 && <div className="group-title" style={{ marginBottom: 10 }}>Post these first</div>}
                {tab === "all" && !needle && i === 3 && <div className="group-title" style={{ margin: "14px 4px 10px" }}>More picks</div>}
                <PromoCard promo={p} decision={decisions[p.id]} onDecide={(status, reason) => onDecide(p.id, status, reason)} />
              </div>
            ))}
            {list.length > shown.length && (
              <div style={{ textAlign: "center", padding: 6 }}>
                <button className="btn" onClick={() => setLimit((l) => l + 20)}>Show {Math.min(20, list.length - shown.length)} more</button>
              </div>
            )}
          </div>
        </div>
      </section>
    </>
  );
}

function safeFormat(pattern) {
  return pattern.replace(/\{ep(?::0?(\d+)d)?\}/g, (_, w) => String(1).padStart(+(w || 1), "0"));
}
