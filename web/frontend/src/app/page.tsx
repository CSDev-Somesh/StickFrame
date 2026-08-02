"use client";

import { useCallback, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { oneDark } from "@codemirror/theme-one-dark";
import { EditorView } from "@codemirror/view";
import { syntaxHighlighting, defaultHighlightStyle, StreamLanguage } from "@codemirror/language";

const sfLanguage = StreamLanguage.define({
  token(stream) {
    if (stream.match(/^#.*/)) return "comment";
    if (stream.match(/^scene\b/)) return "keyword";
    if (stream.match(/^character\b/)) return "keyword";
    if (stream.match(/^camera\b/)) return "keyword";
    if (stream.match(/^timeline\b/)) return "keyword";
    if (stream.match(/^rig\b/)) return "keyword";
    if (stream.match(/^appearance\b/)) return "keyword";
    if (stream.match(/^position\b/)) return "keyword";
    if (stream.match(/^scale\b/)) return "keyword";
    if (stream.match(/^follow\b/)) return "keyword";
    if (stream.match(/^zoom\b/)) return "attribute";
    if (stream.match(/^intensity\b/)) return "attribute";
    if (stream.match(/^duration\b/)) return "attribute";
    if (stream.match(/^speed\b/)) return "attribute";
    if (stream.match(/^idle|walk|run|jump|punch|wave|fall/)) return "string";
    if (stream.match(/^zoom_to\b/)) return "builtin";
    if (stream.match(/^shake\b/)) return "builtin";
    if (stream.match(/^activate\b/)) return "builtin";
    if (stream.match(/^pan_to\b/)) return "builtin";
    if (stream.match(/^reset\b/)) return "builtin";
    if (stream.match(/^follow\b/)) return "builtin";
    if (stream.match(/"[^"]*"/)) return "string";
    if (stream.match(/\d+\.?\d*/)) return "number";
    if (stream.match(/[a-zA-Z_]\w*/)) return "variable";
    stream.next();
    return null;
  },
});

const DEFAULT_SCRIPT = `# StickFrame — Kung Fu Demo (v3 rig with outfit)
scene dojo width=800 height=600 fps=24

camera main:
    follow fighter
    zoom 1.0

character fighter:
    rig bipedal
    appearance head_color="#FFD700" shirt_color="#2E86DE" pants_color="#1B2A4A" shoe_color="#8B4513" skin_color="#FFDAB9"
    scale=2.5
    position (400, 374)

timeline:
    scene dojo:
        0.0s     fighter.idle
        0.6s     fighter.punch
        1.2s     fighter.jump
        2.0s     fighter.idle
`;

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [script, setScript] = useState(DEFAULT_SCRIPT);
  const [rendering, setRendering] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [renderInfo, setRenderInfo] = useState<{ frames: number; duration: number } | null>(null);
  const [view, setView] = useState<"split" | "script" | "video">("split");

  const handleRender = useCallback(async () => {
    setRendering(true);
    setError(null);
    setVideoUrl(null);
    setRenderInfo(null);

    try {
      const res = await fetch(`${API_URL}/api/render`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ script }),
      });

      if (!res.ok) {
        const err = await res.text();
        throw new Error(err);
      }

      const data = await res.json();
      const videoFullUrl = `${API_URL}${data.video_url}`;
      const finalUrl = `${videoFullUrl}?t=${Date.now()}`;
      setVideoUrl(finalUrl);
      setRenderInfo({ frames: data.frames, duration: data.duration });
    } catch (e: any) {
      setError(e.message || "Render failed");
    } finally {
      setRendering(false);
    }
  }, [script]);

  return (
    <div className="flex flex-col h-screen bg-zinc-950 text-zinc-100">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-zinc-800 bg-zinc-900">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold tracking-tight">
            <span className="text-amber-400">Stick</span>Frame
          </h1>
          <span className="text-xs text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded">alpha</span>
        </div>
        <div className="flex items-center gap-2">
          {/* View toggle */}
          <div className="flex bg-zinc-800 rounded p-1" role="group" aria-label="View mode">
            {["split", "script", "video"].map((mode) => (
              <button
                key={mode}
                onClick={() => setView(mode as any)}
                className={`px-3 py-1.5 text-sm rounded transition-all ${
                  view === mode
                    ? "bg-amber-500 text-black font-medium"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
                aria-pressed={view === mode}
              >
                {mode.charAt(0).toUpperCase() + mode.slice(1)}
              </button>
            ))}
          </div>
          <button
            onClick={handleRender}
            disabled={rendering}
            className="bg-amber-500 hover:bg-amber-400 disabled:bg-zinc-700 disabled:text-zinc-500 text-black font-medium px-5 py-1.5 rounded text-sm transition-all"
          >
            {rendering ? (
              <span className="flex items-center gap-2">
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Rendering...
              </span>
            ) : "Render"}
          </button>
        </div>
      </header>

      {/* Main content - horizontal layout with toggle */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {/* Script panel - always visible in split/script mode */}
        {(view === "split" || view === "script") && (
          <div className={`flex flex-col ${view === "split" ? "h-1/2" : "h-full"} border-b border-zinc-800`}>
            <div className="flex items-center justify-between px-4 py-2 text-xs text-zinc-500 bg-zinc-900/50 border-b border-zinc-800">
              <span>script.sf</span>
              <span className="text-zinc-600">{script.split("\n").length} lines</span>
            </div>
            <div className="flex-1 overflow-auto">
              <CodeMirror
                value={script}
                onChange={(val) => setScript(val)}
                extensions={[
                  oneDark,
                  syntaxHighlighting(defaultHighlightStyle),
                  sfLanguage,
                  EditorView.lineWrapping,
                ]}
                theme="dark"
                height="100%"
                basicSetup={{
                  lineNumbers: true,
                  foldGutter: false,
                  highlightActiveLine: true,
                  autocompletion: false,
                }}
              />
            </div>
          </div>
        )}

        {/* Video/Preview panel - always visible in split/video mode */}
        {(view === "split" || view === "video") && (
          <div className={`flex flex-col ${view === "split" ? "h-1/2" : "h-full"} bg-zinc-900`}>
            <div className="flex items-center justify-between px-4 py-2 text-xs text-zinc-500 bg-zinc-900/50 border-b border-zinc-800">
              <span>Preview</span>
              {renderInfo && (
                <span className="text-zinc-400">
                  {renderInfo.frames} frames · {renderInfo.duration.toFixed(1)}s
                </span>
              )}
            </div>
            <div className="flex-1 flex items-center justify-center p-4">
              {videoUrl ? (
                <div className="w-full max-w-3xl">
                  <video
                    src={videoUrl}
                    controls
                    autoPlay
                    loop
                    className="w-full rounded-lg border border-zinc-700 bg-black"
                    style={{ aspectRatio: "4/3" }}
                  />
                </div>
              ) : (
                <div className="text-center text-zinc-600">
                  <svg className="mx-auto h-16 w-16 mb-4 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                  <p className="text-sm">Write a script and hit Render</p>
                </div>
              )}
            </div>
            {error && (
              <div className="px-4 py-3 bg-red-900/50 border-t border-red-800 text-red-300 text-sm">
                {error}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}