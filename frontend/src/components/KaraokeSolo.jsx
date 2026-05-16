import { Mic2, Music2, QrCode, RefreshCw, Trophy, Waves } from "lucide-react";
import { useEffect, useState } from "react";

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.error || `Request failed: ${response.status}`);
  }
  return data;
}

function ScoreBar({ label, value }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-zinc-400">
        <span>{label}</span>
        <span className="tabular-nums">{value}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
        <div
          className="h-full rounded-full bg-teal-300 transition-all"
          style={{ width: `${Math.max(0, Math.min(value, 100))}%` }}
        />
      </div>
    </div>
  );
}

export default function KaraokeSolo({ track, isInstrumental, onUseInstrumental, onTrackUpdated }) {
  const isSecureContext = window.location.protocol === "https:";
  const [stemStatus, setStemStatus] = useState("unprepared");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [score, setScore] = useState(null);
  const [isPreparing, setIsPreparing] = useState(false);
  const [isWaiting, setIsWaiting] = useState(false);

  useEffect(() => {
    setScore(null);
    setMessage("");
    setError("");
    if (!track?.id) return undefined;
    let cancelled = false;

    async function loadState() {
      try {
        const state = await fetchJson(`/api/stems/${track.id}`);
        if (cancelled) return;
        setStemStatus(state.status);
        if (state.track) onTrackUpdated?.(state.track);
        if (state.status === "ready") {
          setIsPreparing(false);
        }
        if (state.status === "error") {
          setIsPreparing(false);
          setError(state.error || "Could not prepare karaoke stems.");
        }
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    }

    loadState();
    return () => {
      cancelled = true;
    };
  }, [track?.id]);

  useEffect(() => {
    if (!isPreparing || !track?.id) return undefined;
    const interval = window.setInterval(async () => {
      try {
        const state = await fetchJson(`/api/stems/${track.id}`);
        setStemStatus(state.status);
        if (state.track) onTrackUpdated?.(state.track);
        if (state.status === "ready") {
          setIsPreparing(false);
          setMessage("Karaoke backing is ready.");
        }
        if (state.status === "error") {
          setIsPreparing(false);
          setError(state.error || "Could not prepare karaoke stems.");
        }
      } catch (err) {
        setIsPreparing(false);
        setError(err.message);
      }
    }, 2500);
    return () => window.clearInterval(interval);
  }, [isPreparing, track?.id]);

  useEffect(() => {
    if (!isWaiting || !track?.id) return undefined;
    const interval = window.setInterval(async () => {
      try {
        const status = await fetchJson("/api/karaoke/status");
        if (status.error) {
          setError(status.error);
          setIsWaiting(false);
        }
        if (status.ready) {
          const result = await fetchJson(`/api/score?track_id=${track.id}`);
          setScore(result.score);
          setIsWaiting(false);
          setMessage("Score ready.");
        }
      } catch (err) {
        setError(err.message);
        setIsWaiting(false);
      }
    }, 1500);
    return () => window.clearInterval(interval);
  }, [isWaiting, track?.id]);

  async function prepareStems() {
    if (!track?.id) return;
    setError("");
    setMessage("Preparing karaoke backing. This can take a while the first time.");
    setIsPreparing(true);
    try {
      const state = await fetchJson(`/api/stems/${track.id}/prepare`, { method: "POST" });
      setStemStatus(state.status);
      if (state.track) onTrackUpdated?.(state.track);
      if (state.status === "ready") {
        setIsPreparing(false);
        setMessage("Karaoke backing is ready.");
      }
    } catch (err) {
      setIsPreparing(false);
      setError(err.message);
    }
  }

  async function startTake() {
    if (!track?.id) return;
    setScore(null);
    setError("");
    setMessage("Scan the QR, start recording on your phone, then play the backing track.");
    await fetchJson("/api/karaoke/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ track_id: track.id }),
    });
    setIsWaiting(true);
  }

  const ready = stemStatus === "ready";

  return (
    <section className="rounded-md border border-zinc-800 bg-[#171a1d]">
      <div className="flex items-center justify-between gap-3 border-b border-zinc-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <Mic2 className="h-4 w-4 text-amber-300" aria-hidden="true" />
          <h3 className="text-sm font-semibold text-zinc-100">Solo karaoke</h3>
        </div>
        <span className="rounded-md border border-amber-400/30 bg-amber-400/10 px-2 py-1 text-xs text-amber-100">
          {ready ? "ready" : stemStatus}
        </span>
      </div>

      <div className="border-b border-zinc-800 px-4 py-2 text-sm">
        {!isSecureContext ? (
          <p className="text-amber-200">
            Microphone access requires HTTPS. Open this app at https://localhost:5173 or
            https://&lt;your-mac-ip&gt;:5173 (not http).
          </p>
        ) : (
          <p className="text-zinc-500">
            First time? On mobile, accept the security warning to enable mic access.
          </p>
        )}
        {message && <p className="mt-2 text-zinc-300">{message}</p>}
        {error && <p className="mt-2 text-rose-200">{error}</p>}
      </div>

      <div className="grid gap-4 p-4 lg:grid-cols-[220px_minmax(0,1fr)]">
        <div className="flex flex-col items-center gap-3 rounded-md border border-zinc-800 bg-[#101214] p-3">
          <img
            src={track ? `/api/karaoke/qr?track_id=${track.id}` : ""}
            alt="Phone mic QR"
            className="h-44 w-44 rounded-md bg-white p-2"
          />
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <QrCode className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Phone mic page</span>
          </div>
        </div>

        <div className="space-y-3">
          <div className="grid gap-2 sm:grid-cols-3">
            <button
              type="button"
              onClick={prepareStems}
              disabled={isPreparing || ready}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-zinc-700 bg-[#101214] px-3 text-sm font-medium text-zinc-100 transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isPreparing ? (
                <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Waves className="h-4 w-4" aria-hidden="true" />
              )}
              Prepare
            </button>
            <button
              type="button"
              onClick={() => onUseInstrumental?.(!isInstrumental)}
              disabled={!ready}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-teal-500/40 bg-teal-500/15 px-3 text-sm font-medium text-teal-100 transition hover:bg-teal-500/25 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Music2 className="h-4 w-4" aria-hidden="true" />
              {isInstrumental ? "Use original" : "Use backing"}
            </button>
            <button
              type="button"
              onClick={startTake}
              disabled={!ready || isWaiting}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-amber-400/50 bg-amber-400/15 px-3 text-sm font-medium text-amber-100 transition hover:bg-amber-400/25 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isWaiting ? (
                <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Trophy className="h-4 w-4" aria-hidden="true" />
              )}
              Start take
            </button>
          </div>

          {score ? (
            <div className="rounded-md border border-zinc-800 bg-[#101214] p-4">
              <div className="mb-4 flex items-center justify-between">
                <span className="text-sm font-medium text-zinc-100">Score</span>
                <span className="text-3xl font-semibold text-amber-200">{score.total}</span>
              </div>
              <div className="space-y-3">
                <ScoreBar label="Pitch" value={score.pitch} />
                <ScoreBar label="Timing" value={score.timing} />
                <ScoreBar label="Consistency" value={score.consistency} />
                <ScoreBar label="Completion" value={score.completion} />
              </div>
            </div>
          ) : (
            <div className="rounded-md border border-zinc-800 bg-[#101214] p-4 text-sm leading-6 text-zinc-400">
              Prepare stems once, switch to the backing track, scan the QR on your phone, then start a take.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
