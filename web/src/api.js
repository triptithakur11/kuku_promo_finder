// Empty in local dev (same origin). On Vercel, set VITE_API_BASE to the Render API URL.
const API = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

async function json(r) {
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || `Request failed (${r.status})`);
  return d;
}

export const getConfig = () => fetch(API + "/api/config").then(json);
export const listRuns = () => fetch(API + "/api/runs").then(json);
export const getRun = (slug) => fetch(`${API}/api/runs/${slug.split("/").map(encodeURIComponent).join("/")}`).then(json);
export const getJob = (id) => fetch(`${API}/api/jobs/${id}`).then(json);
export const startRun = (fd) => fetch(API + "/api/run", { method: "POST", body: fd }).then(json);
export const estimate = (fd) => fetch(API + "/api/estimate", { method: "POST", body: fd }).then(json);

export async function csvFor(promos) {
  const r = await fetch(API + "/api/csv", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(promos),
  });
  return r.text();
}

export function download(name, text, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export const usesAI = (model) => !["", "none", "rules", "offline"].includes((model || "").trim().toLowerCase());

// "LADY JULIANA (Outraged): You knew!" -> "You knew!"  ·  "[ACTION] She slaps him" -> "She slaps him"
export function plainLine(s = "") {
  const t = s.replace(/^\[[A-Z ]+\]\s*/, "");
  const m = t.match(/^[A-Z][A-Z .'’()-]+(?:\([^)]*\))?:\s*(.+)$/);
  return (m ? m[1] : t).replace(/^"|"$/g, "");
}

export const decide = (slug, promo_id, status, reason = "") =>
  fetch(`${API}/api/decisions/${slug}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ promo_id, status, reason }),
  }).then(json);

export const getFeedback = (slug) => fetch(`${API}/api/feedback/${slug}`).then(json);

export async function exportEdit(promos, fps, video_pattern) {
  const r = await fetch(API + "/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ promos, fps, video_pattern }),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Export failed");
  return r.blob();
}

export function downloadBlob(name, blob) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export const REJECT_REASONS = ["Needs backstory", "Weak hook", "Ending resolves too much", "Bad cut point", "Too similar to another", "Other"];
