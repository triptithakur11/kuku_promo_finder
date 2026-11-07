import { useState } from "react";
import { plainLine, REJECT_REASONS } from "../api.js";
import { Check, X, FileText, Alert } from "./Icons.jsx";

function Score({ label, value }) {
  const v = Math.max(0, Math.min(10, Number(value) || 0));
  return (
    <div className="score">
      <div className="lbl"><span>{label}</span><b>{v}/10</b></div>
      <div className="track"><div style={{ width: `${v * 10}%` }} /></div>
    </div>
  );
}

const cut = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

// decision: undefined | {status: "approved"|"rejected", reason}
export default function PromoCard({ promo: p, decision, onDecide }) {
  const [open, setOpen] = useState(null); // "script" | "warnings" | "reject" | null
  const sc = p.scores || {};
  const hasAI = sc.hook != null;
  const first = p.segments[0];
  const status = decision?.status;
  const title = p.source === "rules" || !p.title ? `Episode ${p.episodes.join(" + ")} · ${first.start}` : p.title;
  const why = p.source === "rules" ? "Picked by keyword rules: a strong opening line and a cliffhanger cue at the end." : p.why;
  const toggle = (k) => setOpen((o) => (o === k ? null : k));

  return (
    <article className={`card promo ${status || ""}`}>
      <div className="phone" aria-hidden>
        <span className="rank">{p.rank}</span>
        <span className="dur">{Math.round(p.duration)}s</span>
        <div className="cap top"><small>OPENS ON</small>{cut(plainLine(p.hook), 80)}</div>
        <span className="play" />
        <div className="cap"><small>CUTS ON</small>{cut(plainLine(p.cliffhanger), 64)}</div>
      </div>

      <div className="promo-body">
        <div className="promo-head">
          <h4>{title}</h4>
          <div className="chips" style={{ marginTop: 0 }}>
            {status === "approved" && <span className="pill sm green"><Check size={13} /> Approved</span>}
            {status === "rejected" && <span className="pill sm orange"><X size={13} /> Rejected{decision.reason ? ` · ${decision.reason}` : ""}</span>}
            {!status && p.rank <= 3 && <span className="pill sm green">Post first</span>}
            {p.kind === "montage" && <span className="pill sm purple">Multi-episode</span>}
            {p.kind === "multi" && <span className="pill sm">{p.segments.length} cuts</span>}
            <span className="pill sm">{Math.round(p.duration)}s</span>
          </div>
        </div>

        <div className="timeline" aria-label="Segments in order">
          {p.segments.map((s, i) => (
            <span key={i} style={{ display: "contents" }}>
              {i > 0 && <span className="then">then</span>}
              <span className="seg"><b>Ep {s.episode}</b>{s.start} → {s.end}</span>
            </span>
          ))}
        </div>

        <div className="facts">
          <div className="fact"><span className="k">Hook</span><span>{p.hook}</span></div>
          <div className="fact"><span className="k">Cliffhanger</span><span>{p.cliffhanger}</span></div>
          <div className="fact"><span className="k">Why it works</span><span>{why}</span></div>
          {p.rank_reason && !p.rank_reason.startsWith("score") && (
            <div className="fact"><span className="k">Why #{p.rank}</span><span>{p.rank_reason}</span></div>
          )}
          {p.context_needed && <div className="fact"><span className="k">Might confuse</span><span className="muted">{p.context_needed}</span></div>}
          {(p.tropes || []).length > 0 && (
            <div className="fact"><span className="k">Tropes</span><span className="chips" style={{ marginTop: 0 }}>{p.tropes.slice(0, 4).map((t) => <span key={t} className="pill sm">{t}</span>)}</span></div>
          )}
        </div>

        {hasAI ? (
          <div className="scores">
            <Score label="Hook" value={sc.hook} />
            <Score label="Cliffhanger" value={sc.cliffhanger} />
            <Score label="Makes sense alone" value={sc.standalone} />
          </div>
        ) : (
          <div className="scores" style={{ gridTemplateColumns: "minmax(0, 1fr)" }}>
            <Score label="Rule score" value={Math.round(p.final_score * 100) / 10} />
          </div>
        )}

        <div className="promo-foot">
          <div className="links">
            <button className="link" onClick={() => toggle("script")}><FileText size={16} />{open === "script" ? "Hide script" : "Read the script"}</button>
            {p.flags.length > 0 && (
              <button className="link warn" onClick={() => toggle("warnings")}>
                <Alert size={16} />{p.flags.length} thing{p.flags.length > 1 ? "s" : ""} to check
              </button>
            )}
          </div>
          <div className="decide">
            {status ? (
              <button className="btn" onClick={() => { onDecide(null); setOpen(null); }}>Undo</button>
            ) : (
              <>
                <button className={`btn ${open === "reject" ? "reject-on" : ""}`} onClick={() => toggle("reject")}><X size={16} /> Reject</button>
                <button className="btn approve" onClick={() => onDecide("approved")}><Check size={16} /> Approve</button>
              </>
            )}
          </div>
        </div>

        {open === "reject" && !status && (
          <div className="drawer">
            <div style={{ marginBottom: 8, fontWeight: 600 }}>Why isn’t it a good promo? This helps tune the tool.</div>
            <div className="chips">
              {REJECT_REASONS.map((r) => (
                <button key={r} className="pill reason" onClick={() => { onDecide("rejected", r); setOpen(null); }}>{r}</button>
              ))}
            </div>
          </div>
        )}
        {open === "script" && <div className="drawer"><pre>{p.excerpt.join("\n")}</pre></div>}
        {open === "warnings" && <div className="drawer"><ul>{p.flags.map((f, i) => <li key={i}>{f}</li>)}</ul></div>}
      </div>
    </article>
  );
}
