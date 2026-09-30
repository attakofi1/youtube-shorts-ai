"use client";

import { FormEvent, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [url, setUrl] = useState("");
  const [clips, setClips] = useState(10);
  const [duration, setDuration] = useState("20-60");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setStatus("Starting AI processing...");
    try {
      const [min, max] = duration.split("-").map(Number);
      const response = await fetch(`${API}/api/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ youtube_url: url, clips, min_duration: min, max_duration: max }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Failed to create job");
      setStatus(`Job ${data.job_id} queued. Your Shorts are being generated.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <section className="hero">
        <span className="badge">AI VIDEO REPURPOSING</span>
        <h1>Long video → many Shorts</h1>
        <p>Paste a YouTube video and generate multiple vertical clips from the strongest moments.</p>
      </section>

      <section className="card">
        <form onSubmit={submit}>
          <label htmlFor="url">YouTube URL</label>
          <input id="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=..." required />
          <div className="grid">
            <div><label htmlFor="clips">Number of Shorts</label><select id="clips" value={clips} onChange={(e) => setClips(Number(e.target.value))}>{[5,10,15,20,30,50].map(n => <option key={n} value={n}>{n} Shorts</option>)}</select></div>
            <div><label htmlFor="duration">Clip duration</label><select id="duration" value={duration} onChange={(e) => setDuration(e.target.value)}><option value="15-30">15–30 sec</option><option value="20-60">20–60 sec</option><option value="30-90">30–90 sec</option><option value="45-120">45–120 sec</option></select></div>
            <div><label>Output</label><input value="1080 × 1920" readOnly /></div>
          </div>
          <button className="primary" disabled={busy}>{busy ? "Processing..." : "Generate Shorts"}</button>
          {status && <div className="status">{status}</div>}
        </form>
      </section>

      <section className="features">
        <div className="feature"><h3>AI transcription</h3><p>Whisper converts speech into timestamped segments for clip analysis.</p></div>
        <div className="feature"><h3>Batch rendering</h3><p>Generate many vertical MP4 clips from one long source.</p></div>
        <div className="feature"><h3>Shorts format</h3><p>1080 × 1920 output with fast FFmpeg processing.</p></div>
      </section>
    </main>
  );
}
