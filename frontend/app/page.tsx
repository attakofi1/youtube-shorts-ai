"use client";

import { FormEvent, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
type Clip = { file: string; start: number; end: number; score: number; text: string; hook?: string; title?: string; rank: number };

export default function Home() {
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [clips, setClips] = useState(10);
  const [duration, setDuration] = useState("20-60");
  const [status, setStatus] = useState("");
  const [progress, setProgress] = useState(0);
  const [jobId, setJobId] = useState("");
  const [results, setResults] = useState<Clip[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!jobId) return;
    let stopped = false;
    const poll = async () => {
      try {
        const response = await fetch(`${API}/api/jobs/${jobId}`, { cache: "no-store" });
        const data = await response.json();
        if (stopped) return;
        setProgress(data.progress || (data.status === "SUCCESS" ? 100 : 0));
        setStatus(data.message || data.status || "Processing...");
        if (data.status === "SUCCESS") { setResults(data.result?.clips || []); setBusy(false); return; }
        if (data.status === "FAILURE") { setBusy(false); setStatus(data.error || "Processing failed"); return; }
        window.setTimeout(poll, 1800);
      } catch { if (!stopped) window.setTimeout(poll, 3000); }
    };
    poll();
    return () => { stopped = true; };
  }, [jobId]);

  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setResults([]); setProgress(0); setStatus("Queueing your video...");
    try {
      const [min, max] = duration.split("-").map(Number);
      let response: Response;
      if (file) {
        const form = new FormData();
        form.append("video", file);
        form.append("clips", String(clips));
        form.append("min_duration", String(min));
        form.append("max_duration", String(max));
        response = await fetch(`${API}/api/jobs/upload`, { method: "POST", body: form });
      } else {
        response = await fetch(`${API}/api/jobs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ youtube_url: url, clips, min_duration: min, max_duration: max }) });
      }
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Failed to create job");
      setJobId(data.job_id);
    } catch (error) { setBusy(false); setStatus(error instanceof Error ? error.message : "Something went wrong"); }
  }

  return <main className="shell">
    <section className="hero"><span className="badge">AI VIDEO REPURPOSING</span><h1>Long video → many Shorts</h1><p>AI finds strong moments, tracks the speaker, crops vertically, and adds captions.</p></section>
    <section className="card"><form onSubmit={submit}>
      <label htmlFor="url">YouTube URL</label><input id="url" value={url} onChange={(e) => { setUrl(e.target.value); if (e.target.value) setFile(null); }} placeholder="https://www.youtube.com/watch?v=..." disabled={!!file} required={!file} /><div className="or">or upload a video</div><input id="file" type="file" accept="video/mp4,video/quicktime,video/webm,video/x-matroska,video/x-m4v" onChange={(e) => { const selected = e.target.files?.[0] || null; setFile(selected); if (selected) setUrl(""); }} />
      <div className="grid"><div><label htmlFor="clips">Number of Shorts</label><select id="clips" value={clips} onChange={(e) => setClips(Number(e.target.value))}>{[5,10,15,20,30,50].map(n => <option key={n} value={n}>{n} Shorts</option>)}</select></div><div><label htmlFor="duration">Clip duration</label><select id="duration" value={duration} onChange={(e) => setDuration(e.target.value)}><option value="15-30">15–30 sec</option><option value="20-60">20–60 sec</option><option value="30-90">30–90 sec</option><option value="45-120">45–120 sec</option></select></div><div><label>Output</label><input value="1080 × 1920" readOnly /></div></div>
      <button className="primary" disabled={busy}>{busy ? "Generating Shorts..." : "Generate Shorts"}</button>
      {busy && <div className="progress"><div className="bar" style={{ width: `${progress}%` }} /></div>}
      {status && <div className="status">{status} {busy && progress ? `${progress}%` : ""}</div>}
    </form></section>
    {results.length > 0 && <section className="results"><div className="resultsHead"><h2>Generated Shorts</h2><span>{results.length} clips</span>{results.length > 0 && <a className="downloadAll" href={`${API}/api/jobs/${jobId}/download`}>Download all ZIP</a>}</div><div className="gallery">{results.map((clip) => <article className="clip" key={clip.file}><video src={`${API}/api/jobs/${jobId}/clips/${clip.file}`} controls preload="metadata" /><div className="clipBody"><b>{clip.title || `Short ${clip.rank}`}</b><small>Score {clip.score} · {Math.round(clip.end - clip.start)} sec</small><p>{clip.hook || clip.text}</p><a href={`${API}/api/jobs/${jobId}/clips/${clip.file}`} download>Download MP4</a></div></article>)}</div></section>}
    <section className="features"><div className="feature"><h3>Smart framing</h3><p>Face detection keeps the main speaker inside the vertical frame.</p></div><div className="feature"><h3>Readable captions</h3><p>Whisper word timestamps create short subtitle groups automatically.</p></div><div className="feature"><h3>Parallel rendering</h3><p>Multiple clips render concurrently to reduce batch processing time.</p></div></section>
  </main>;
}
