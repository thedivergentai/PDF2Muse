import { useEffect, useRef, useState } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

const SIDECAR = "http://127.0.0.1:8765";

export default function App() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState("Idle");
  const [musicXml, setMusicXml] = useState<string | null>(null);

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

  async function startJob(pdfPath: string) {
    setStatus("Submitting job…");
    const response = await fetch(`${SIDECAR}/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pdf_path: pdfPath,
        output_dir: "output",
        model_backend: "auto",
        oemer_quality_profile: "quality",
      }),
    });
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
      if (payload.status === "completed" && payload.result_path) {
        window.clearInterval(interval);
        const xmlPath = payload.result_path.replace(/\.mscx$/, ".musicxml");
        const xmlResponse = await fetch(`file://${xmlPath}`);
        if (xmlResponse.ok) {
          setMusicXml(await xmlResponse.text());
        }
      }
      if (payload.status === "failed") {
        window.clearInterval(interval);
      }
    }, 1000);
    return () => window.clearInterval(interval);
  }, [jobId]);

  return (
    <main style={{ fontFamily: "Inter, system-ui, sans-serif", padding: 24 }}>
      <h1>PDF2Muse Desktop</h1>
      <p>Local-first shell with OSMD viewer and Python sidecar on port 8765.</p>
      <button type="button" onClick={() => startJob("sample.pdf")}>
        Demo job (configure PDF path)
      </button>
      <p>{status}</p>
      <div
        ref={containerRef}
        style={{
          marginTop: 16,
          minHeight: 480,
          border: "1px solid #444",
          borderRadius: 8,
        }}
      />
    </main>
  );
}
