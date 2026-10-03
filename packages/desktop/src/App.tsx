import { useEffect, useRef, useState } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

const SIDECAR = "http://127.0.0.1:8765";

export default function App() {
  const containerRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState("Idle");
  const [musicXml, setMusicXml] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!containerRef.current || !musicXml) return;
    const osmd = new OpenSheetMusicDisplay(containerRef.current, {
      autoResize: true,
      drawTitle: true,
    });
    osmd.load(musicXml).then(() => osmd.render());
    return () => {
      containerRef.current!.innerHTML = "";
    };
  }, [musicXml]);

  async function uploadPdf(file: File) {
    setBusy(true);
    setStatus("Uploading…");
    const body = new FormData();
    body.append("file", file);
    const response = await fetch(`${SIDECAR}/jobs/upload`, {
      method: "POST",
      body,
    });
    if (!response.ok) {
      setBusy(false);
      setStatus(`Upload failed (${response.status})`);
      return;
    }
    const payload = await response.json();
    setJobId(payload.job_id);
    setStatus("Running…");
  }

  useEffect(() => {
    if (!jobId) return;
    const interval = window.setInterval(async () => {
      const response = await fetch(`${SIDECAR}/jobs/${jobId}`);
      const payload = await response.json();
      setStatus(`${payload.status}: ${payload.message}`);
      if (payload.status === "completed") {
        window.clearInterval(interval);
        const xmlResponse = await fetch(`${SIDECAR}/jobs/${jobId}/musicxml`);
        if (xmlResponse.ok) {
          setMusicXml(await xmlResponse.text());
        } else {
          setStatus("Completed, but MusicXML could not be loaded from the sidecar.");
        }
        setBusy(false);
      }
      if (payload.status === "failed") {
        window.clearInterval(interval);
        setBusy(false);
      }
    }, 1000);
    return () => window.clearInterval(interval);
  }, [jobId]);

  return (
    <main>
      <h1>PDF2Muse Desktop</h1>
      <p>
        Local-first shell. Pick a PDF, wait for the sidecar, then review the draft in
        OpenSheetMusicDisplay. Output is experimental — edit it in MuseScore before use.
      </p>
      <input
        ref={fileRef}
        type="file"
        accept="application/pdf,.pdf"
        disabled={busy}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void uploadPdf(file);
        }}
      />
      <p>{status}</p>
      <div ref={containerRef} className="osmd-host" />
    </main>
  );
}
