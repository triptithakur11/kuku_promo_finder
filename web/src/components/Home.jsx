import { useEffect, useRef, useState } from "react";
import { estimate, usesAI } from "../api.js";
import ModelSelect from "./ModelSelect.jsx";
import {
  Sparkle, Upload, FileText, Zap, Hourglass, Eye, Shield, Check, X, Clock, UserCheck, Layers, Alert, Crown, ArrowRight, Film,
} from "./Icons.jsx";

export default function Home({ config, runs, error, onRun, onOpen }) {
  const [file, setFile] = useState(null);
  const [info, setInfo] = useState(null);
  const [infoErr, setInfoErr] = useState("");
  const [drag, setDrag] = useState(false);
  const [model, setModel] = useState(config.default_model);
  const [apiKey, setApiKey] = useState("");
  const [episodes, setEpisodes] = useState("");
  const [montages, setMontages] = useState(4);
  const [judge, setJudge] = useState(true);
  const input = useRef(null);
  const ai = usesAI(model);
  const provider = (model.split(":")[0] || "").toLowerCase();
  const keyMissing = ai && config.keys && config.keys[provider] === false && !apiKey;

  useEffect(() => setModel(config.default_model), [config.default_model]);

  // Free, local check of the file: episodes found and how many AI requests a run would use.
  useEffect(() => {
    if (!file) return;
    const t = setTimeout(() => {
      estimate(form(false)).then((d) => { setInfo(d); setInfoErr(""); }).catch((e) => { setInfo(null); setInfoErr(e.message); });
    }, 250);
    return () => clearTimeout(t);
  }, [file, episodes, montages, judge, model]);

  function form(withKey = true) {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("model", model);
    if (withKey) fd.append("api_key", apiKey);
    fd.append("episodes", episodes);
    fd.append("montages", String(ai ? montages : 0));
    fd.append("judge", ai && judge ? "true" : "false");
    return fd;
  }
  const pick = (f) => { if (f) { setFile(f); setInfo(null); setInfoErr(""); } };

  return (
    <>
      <section className="hero">
        <div>
          <span className="pill accent"><Sparkle size={16} /> AI Promo Finder</span>
          <h2>Upload a show. Get its best promo clips, ranked.</h2>
          <p>
            Today an editor watches every episode to find ad moments. Promo Finder reads the screenplays and picks 20–60
            second clips that open on a hook, end on a cliffhanger, and make sense to someone who has never seen the show.
          </p>
          <div className="pills">
            <span className="pill yellow"><Shield size={16} /> You approve every clip before it’s posted</span>
            <span className="pill accent-outline"><Crown size={16} /> Ranked by what to post first</span>
          </div>
        </div>
        <div className="preview" aria-hidden>
          <span className="pill accent sm"><Film size={14} /> Episode 1 · 00:39</span>
          <div className="bubble">“Because he is marrying me.”</div>
          <div className="preview-card">
            <b>Promo #1 · Jilted at the altar</b>
            <div className="row"><span>Opens on</span><b>A bride’s sister steals the groom</b></div>
            <div className="row"><span>Cuts on</span><b>“How long?”</b></div>
            <div className="row"><span>Length</span><b style={{ color: "var(--green)" }}>34s ✓</b></div>
            <button className="go" tabIndex={-1}>Approve</button>
          </div>
        </div>
      </section>

      <section className="row-section">
        <div className="row-label">
          <h3>Upload screenplays</h3>
          <p>Add a .zip of timestamped episode scripts, or a single episode .txt. Every line has a time, so every pick maps to real footage.</p>
        </div>
        <div>
          {!file ? (
            <div className={`dropzone ${drag ? "drag" : ""}`} role="button" tabIndex={0}
              onClick={() => input.current?.click()}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files[0]); }}>
              <span className="icon-tile"><Upload size={22} /></span>
              <div className="dz-title">Drop your screenplay pack here</div>
              <div className="dz-sub">.zip or .txt · checked on this computer before anything is sent</div>
              <span className="btn btn-accent">Choose file</span>
            </div>
          ) : (
            <div className="card file-card">
              <span className="icon-tile"><FileText size={22} /></span>
              <div className="grow">
                <div className="name">{info?.show || file.name}</div>
                <div className="chips">
                  {!info && !infoErr && <span className="pill sm">Reading file…</span>}
                  {info && <span className="pill sm green">{info.episodes_found} episodes found</span>}
                  {info && <span className="pill sm">{info.minutes_of_footage} min of footage</span>}
                  {info && (ai
                    ? <span className="pill sm accent">About {info.ai_requests} AI requests</span>
                    : <span className="pill sm">No AI · free</span>)}
                  {info && ai && <span className="pill sm">{fmtMinutes(info.approx_minutes)}</span>}
                  {info?.episode_requests_cached > 0 && ai && <span className="pill sm">{info.episode_requests_cached} cached</span>}
                  {infoErr && <span className="pill sm orange">{infoErr}</span>}
                </div>
              </div>
              <button className="btn" onClick={() => { setFile(null); setInfo(null); }}>Change</button>
            </div>
          )}
          <input ref={input} type="file" accept=".zip,.txt" hidden onChange={(e) => pick(e.target.files[0])} />

          <div className="field" style={{ marginTop: 16 }}>
            <label>AI model</label>
            <ModelSelect value={model} onChange={setModel} keys={config.keys} />
          </div>

          <details className="card settings">
            <summary>
              More options
              <span className="sum">{episodes ? `Episodes ${episodes}` : "All episodes"}{ai ? ` · ${montages} trailers` : ""}</span>
              <svg className="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><path d="M9 6l6 6-6 6" /></svg>
            </summary>
            <div className="form-grid">
              <div className="field">
                <label htmlFor="episodes">Episodes</label>
                <input id="episodes" className="input" placeholder="All episodes" value={episodes} onChange={(e) => setEpisodes(e.target.value)} />
                <div className="hint">e.g. 1-10 or 1,4,7. Start small to save AI credits.</div>
              </div>
              <div className="field">
                <label htmlFor="key">API key</label>
                <input id="key" className="input" type="password" autoComplete="off" disabled={!ai}
                  placeholder={config.keys?.[provider] ? "Using the key from .env" : "Paste a key for this run"}
                  value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
                <div className="hint">Optional. Used for this run only and never saved.</div>
              </div>
              <div className="field">
                <label htmlFor="montages">Multi-episode trailers</label>
                <input id="montages" className="input" type="number" min="0" max="8" disabled={!ai} value={montages}
                  onChange={(e) => setMontages(+e.target.value)} />
                <div className="hint">Promos that join moments from several episodes.</div>
              </div>
              <div className="field" style={{ alignSelf: "center" }}>
                <label className="check-row">
                  <input type="checkbox" disabled={!ai} checked={judge} onChange={(e) => setJudge(e.target.checked)} />
                  Let AI decide the posting order
                </label>
              </div>
            </div>
          </details>

          <div className="run-row">
            <span className="hint"><Shield size={16} /> Nothing gets posted. You review every pick.</span>
            <button className="btn btn-primary btn-lg" disabled={!file || !!infoErr || keyMissing} onClick={() => onRun(form())}>
              Find promos <ArrowRight size={18} />
            </button>
          </div>
          {keyMissing && <div className="error"><Alert size={18} /> This model needs an API key. Add it to .env or paste it under More options.</div>}
          {error && <div className="error"><Alert size={18} /> {error}</div>}
        </div>
      </section>

      <section className="row-section">
        <div className="row-label">
          <h3>What makes a good promo</h3>
          <p>Every clip is judged on the three things that make ReelShort- and DramaBox-style ads work.</p>
        </div>
        <div className="grid-3">
          <div className="card feature"><span className="icon-tile sm"><Zap size={20} /></span><div><b>Hooks in 3 seconds</b><span>A slap, a reveal or a shocking line</span></div></div>
          <div className="card feature"><span className="icon-tile sm orange"><Hourglass size={20} /></span><div><b>Ends unresolved</b><span>Cuts before the answer arrives</span></div></div>
          <div className="card feature"><span className="icon-tile sm green"><Eye size={20} /></span><div><b>Works on its own</b><span>Makes sense with no backstory</span></div></div>
        </div>
      </section>

      <section className="row-section">
        <div className="row-label">
          <h3>Two ways to run</h3>
          <p>Rules only is free and instant, which is handy for a quick look. AI + rules reads the story and gives much better picks. Choose in the model menu.</p>
        </div>
        <div className="grid-2">
          <div className="card level">
            <div className="level-head"><span className="icon-tile sm gray"><Zap size={20} /></span><div><b>Rules only</b><span>No API key needed</span></div></div>
            <ul className="checks">
              <li><span className="ci"><Check size={14} /></span>Instant and free</li>
              <li><span className="ci"><Check size={14} /></span>Spots slaps, reveals and episode-end stingers</li>
              <li className="off"><span className="ci"><X size={14} /></span>Understands the story</li>
            </ul>
          </div>
          <div className="card level selected">
            <div className="level-head"><span className="icon-tile sm"><Sparkle size={20} /></span><div><b>AI + rules</b><span>Recommended</span></div></div>
            <ul className="checks">
              <li><span className="ci"><Check size={14} /></span>Everything in Rules only</li>
              <li><span className="ci"><Check size={14} /></span>Writes the hook, cliffhanger and why it works</li>
              <li><span className="ci"><Check size={14} /></span>Builds multi-episode trailers and a posting order</li>
            </ul>
            <div className="note"><Shield size={18} /> The AI never sets timestamps alone. Code checks each one against the script.</div>
          </div>
        </div>
      </section>

      <section className="row-section">
        <div className="row-label">
          <h3>Always checked</h3>
          <p>These hold for every clip, whichever model you choose.</p>
        </div>
        <div className="grid-2">
          <div className="card feature"><span className="icon-tile sm green"><Clock size={20} /></span><div><b>20–60 seconds</b><span>Clips outside the range are dropped</span></div></div>
          <div className="card feature"><span className="icon-tile sm green"><Layers size={20} /></span><div><b>Never cuts mid-line</b><span>Edges snap to real lines in the script</span></div></div>
          <div className="card feature"><span className="icon-tile sm green"><UserCheck size={20} /></span><div><b>A person approves</b><span>Nothing goes out on its own</span></div></div>
          <div className="card feature"><span className="icon-tile sm green"><FileText size={20} /></span><div><b>Every AI answer saved</b><span>Raw responses are kept for review</span></div></div>
        </div>
      </section>

      <section className="row-section">
        <div className="row-label">
          <h3>Recent results</h3>
          <p>Open a previous run to keep reviewing where you left off.</p>
        </div>
        <div className="card">
          <div className="table-head"><b>{runs.length} saved run{runs.length === 1 ? "" : "s"}</b></div>
          {runs.length === 0 ? (
            <div className="empty-state"><span className="icon-tile gray"><Film size={22} /></span>No runs yet. Upload a show to get started.</div>
          ) : runs.map((r) => (
            <button key={r.slug} className="list-row" onClick={() => onOpen(r.slug)}>
              <span className="icon-tile sm"><Film size={18} /></span>
              <span className="grow">
                <div className="t">{r.show}</div>
                <div className="s">{r.model === "rules-only" ? "Rules only" : r.model} · {r.created}</div>
              </span>
              <span className="pill sm accent">{r.kept} promos</span>
              <ArrowRight size={18} className="muted" />
            </button>
          ))}
        </div>
      </section>
      <footer>Promo Finder finds and ranks clips. Editing, music and text overlays stay with your editors.</footer>
    </>
  );
}

function fmtMinutes([lo, hi] = [0, 0]) {
  if (hi < 1) return "Under a minute";
  const a = Math.max(1, Math.round(lo)), b = Math.max(a, Math.round(hi));
  return a === b ? `About ${a} min` : `About ${a}–${b} min`;
}
