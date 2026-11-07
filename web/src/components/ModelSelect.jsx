import { useEffect, useRef, useState } from "react";
import { Check, Sparkle, Zap, Lock, Settings } from "./Icons.jsx";

// `value` is the provider:model string the backend understands.
export const MODEL_GROUPS = [
  {
    provider: "gemini", label: "Google Gemini",
    options: [
      { value: "gemini:gemini-3.8-flash", name: "Gemini 3.8 Flash", desc: "Newest Flash. Falls back to 3.6 if it's busy", badges: ["Recommended"] },
      { value: "gemini:gemini-3.6-flash", name: "Gemini 3.6 Flash", desc: "Fast and reliable, about 3s per request" },
      { value: "gemini:gemini-3.1-flash-lite", name: "Gemini 3.1 Flash Lite", desc: "Cheapest. Lighter judgement" },
    ],
  },
  {
    provider: "anthropic", label: "Anthropic Claude",
    options: [
      { value: "anthropic:claude-sonnet-5-5", name: "Claude Sonnet 5.5", desc: "Strong story judgement" },
      { value: "anthropic:claude-haiku-5-5", name: "Claude Haiku 5.5", desc: "Fast and low cost" },
    ],
  },
  {
    provider: "groq", label: "Groq",
    options: [{ value: "groq:llama-3.3-70b-versatile", name: "Llama 3.3 70B", desc: "Very fast free tier, tighter limits" }],
  },
  {
    provider: "openai", label: "OpenAI",
    options: [{ value: "openai:gpt-4o-mini", name: "GPT-4o mini", desc: "Low-cost general model" }],
  },
  {
    provider: "ollama", label: "On this computer",
    options: [{ value: "ollama:llama3.1", name: "Llama 3.1 via Ollama", desc: "Private, no key. Needs Ollama running", badges: ["Local"] }],
  },
  {
    provider: "none", label: "No AI",
    options: [{ value: "none", name: "Rules only", desc: "Keyword scoring. Instant, free, weaker picks", badges: ["Free"] }],
  },
];
const ALL = MODEL_GROUPS.flatMap((g) => g.options.map((o) => ({ ...o, provider: g.provider, group: g.label })));
const CUSTOM = "__custom__";

export function describeModel(value) {
  return ALL.find((o) => o.value === value) || { value, name: value, desc: "Custom model", provider: value.split(":")[0] };
}

function ProviderIcon({ provider }) {
  if (provider === "none") return <span className="icon-tile sm gray"><Zap size={18} /></span>;
  if (provider === "ollama") return <span className="icon-tile sm green"><Lock size={18} /></span>;
  if (provider === "custom") return <span className="icon-tile sm gray"><Settings size={18} /></span>;
  return <span className="icon-tile sm"><Sparkle size={18} /></span>;
}

function KeyBadge({ provider, keys }) {
  if (!keys || provider === "none" || provider === "ollama") return null;
  return keys[provider]
    ? <span className="pill sm green">Key set ✓</span>
    : <span className="pill sm orange">Needs key</span>;
}

export default function ModelSelect({ value, onChange, keys }) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [custom, setCustom] = useState(!ALL.some((o) => o.value === value) ? value : "");
  const box = useRef(null);
  const items = [...ALL, { value: CUSTOM, name: "Custom model…", desc: "Any provider:model string, e.g. openrouter:<model>", provider: "custom", group: "Other" }];
  const isCustom = !ALL.some((o) => o.value === value);
  const current = isCustom ? { name: value || "Custom model", desc: "Custom provider:model", provider: "custom" } : describeModel(value);

  useEffect(() => {
    const close = (e) => box.current && !box.current.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  useEffect(() => { if (open) setActive(Math.max(0, items.findIndex((o) => o.value === (isCustom ? CUSTOM : value)))); }, [open]);

  function choose(o) {
    if (o.value === CUSTOM) { onChange(custom || "openrouter:"); }
    else onChange(o.value);
    setOpen(false);
  }
  function onKey(e) {
    if (!open && ["ArrowDown", "Enter", " "].includes(e.key)) { e.preventDefault(); setOpen(true); return; }
    if (!open) return;
    if (e.key === "Escape") setOpen(false);
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(items.length - 1, a + 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    if (e.key === "Enter") { e.preventDefault(); choose(items[active]); }
  }

  let lastGroup = null;
  return (
    <div className="mselect" ref={box}>
      <button type="button" className={`mselect-btn ${open ? "open" : ""}`} onClick={() => setOpen((o) => !o)} onKeyDown={onKey}
        aria-haspopup="listbox" aria-expanded={open}>
        <ProviderIcon provider={current.provider} />
        <span className="mtext">
          <b>{current.name}</b>
          <span>{current.desc}</span>
        </span>
        <KeyBadge provider={current.provider} keys={keys} />
        <svg className="chev" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M6 9l6 6 6-6" /></svg>
      </button>

      {open && (
        <div className="mselect-menu" role="listbox">
          {items.map((o, i) => {
            const header = o.group !== lastGroup ? (lastGroup = o.group) : null;
            const selected = o.value === CUSTOM ? isCustom : o.value === value;
            return (
              <div key={o.value}>
                {header && <div className="mgroup">{header}</div>}
                <div role="option" aria-selected={selected} className={`mopt ${i === active ? "active" : ""} ${selected ? "selected" : ""}`}
                  onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); choose(o); }}>
                  <ProviderIcon provider={o.provider} />
                  <span className="mtext">
                    <b>{o.name} {(o.badges || []).map((b) => <span key={b} className={`pill sm ${b === "Free" || b === "Local" ? "green" : "purple"}`}>{b}</span>)}</b>
                    <span>{o.desc}</span>
                  </span>
                  <KeyBadge provider={o.provider} keys={keys} />
                  <span className="mcheck">{selected && <Check size={18} />}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {isCustom && (
        <input className="input" style={{ marginTop: 8 }} placeholder="provider:model, e.g. openrouter:meta-llama/llama-3.3-70b-instruct"
          value={value} onChange={(e) => { setCustom(e.target.value); onChange(e.target.value); }} />
      )}
    </div>
  );
}
