import { useEffect, useState } from "react";
import { getConfig, listRuns, getRun, getJob, startRun } from "./api.js";
import { ArrowLeft, Film } from "./components/Icons.jsx";
import Home from "./components/Home.jsx";
import Running from "./components/Running.jsx";
import Results from "./components/Results.jsx";

export default function App() {
  const [view, setView] = useState("home");
  const [config, setConfig] = useState({ default_model: "gemini:gemini-3.8-flash", keys: null });
  const [runs, setRuns] = useState([]);
  const [result, setResult] = useState(null);
  const [job, setJob] = useState({ progress: 0, message: "" });
  const [error, setError] = useState("");

  const refreshRuns = () => listRuns().then(setRuns).catch(() => {});

  useEffect(() => {
    getConfig().then(setConfig).catch(() => {});
    refreshRuns();
    const slug = new URLSearchParams(location.search).get("run"); // /?run=<slug> opens a saved run
    if (slug) openRun(slug);
  }, []);

  function openRun(slug) {
    getRun(slug)
      .then((r) => { setResult(r); setView("results"); window.scrollTo(0, 0); })
      .catch((e) => setError(e.message));
  }

  async function run(fd) {
    setError("");
    setJob({ progress: 0, message: "Uploading scripts…" });
    setView("running");
    window.scrollTo(0, 0);
    try {
      const { job_id } = await startRun(fd);
      for (;;) {
        const j = await getJob(job_id);
        setJob({ progress: j.progress, message: j.message });
        if (j.status === "done") { setResult(j.result); setView("results"); refreshRuns(); window.scrollTo(0, 0); return; }
        if (j.status === "error") throw new Error(j.error);
        await new Promise((r) => setTimeout(r, 1200));
      }
    } catch (e) {
      setError(e.message);
      setView("home");
    }
  }

  const head = {
    home: ["Promo Finder", "Find the best 20–60s ad clips in a microdrama screenplay"],
    running: ["Finding promos", "Reading every episode for hooks and cliffhangers"],
    results: [result?.show || "Results", result ? `${result.counts.kept} promos · ${result.model === "rules-only" ? "Rules only" : result.model} · ${result.created}` : ""],
  }[view];

  return (
    <>
      <header className="pagebar">
        <div className="inner">
          {view !== "home" && (
            <button className="round-btn" onClick={() => setView("home")} aria-label="Back to start"><ArrowLeft /></button>
          )}
          <span className="icon-tile"><Film size={22} /></span>
          <div className="titles">
            <h1>{head[0]}</h1>
            <p>{head[1]}</p>
          </div>
          {view === "results" && <button className="btn btn-primary" onClick={() => setView("home")}>New show</button>}
        </div>
      </header>
      <main className="container">
        {view === "home" && <Home config={config} runs={runs} error={error} onRun={run} onOpen={openRun} />}
        {view === "running" && <Running progress={job.progress} message={job.message} />}
        {view === "results" && result && <Results result={result} />}
      </main>
    </>
  );
}
