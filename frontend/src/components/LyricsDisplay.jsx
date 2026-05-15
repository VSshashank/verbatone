import { FileText, Minus, PencilLine, Plus, RefreshCcw, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTTML } from "../hooks/useTTML.js";
import PhoneticLayer from "./PhoneticLayer.jsx";

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.error || `Request failed: ${response.status}`);
  }
  return data;
}

export default function LyricsDisplay({ track, currentTime, onTrackUpdated }) {
  const [ttml, setTtml] = useState("");
  const [lyricsText, setLyricsText] = useState("");
  const [showManual, setShowManual] = useState(false);
  const [isWorking, setIsWorking] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [showPhonetics, setShowPhonetics] = useState(false);
  const [timeOffset, setTimeOffset] = useState(0);
  const activeRef = useRef(null);
  const pollRef = useRef(null);
  const effectiveTime = currentTime + timeOffset;
  const { lines, activeIdx, activeLineIdx, hasPhonetics } = useTTML(ttml, effectiveTime);

  const isPodcast = track?.type === "podcast";

  useEffect(() => {
    setTtml("");
    setLyricsText("");
    setShowManual(false);
    setIsWorking(false);
    setMessage("");
    setError("");
    setShowPhonetics(false);
    setTimeOffset(0);
    if (!track?.id) return undefined;
    loadTtml(track.id);
    if (track.status === "aligning" || track.status === "fetching_lyrics") {
      setIsWorking(true);
      setMessage(isPodcast ? "Transcribing audio..." : "Aligning lyrics...");
      startPolling(track.id);
    }
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [track?.id]);

  useEffect(() => {
    if (activeRef.current) {
      activeRef.current.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [activeLineIdx]);

  async function loadTtml(trackId) {
    try {
      const response = await fetch(`/api/ttml/${trackId}`);
      if (!response.ok) return;
      setTtml(await response.text());
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  function startPolling(trackId) {
    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = window.setInterval(async () => {
      try {
        const result = await fetchJson(`/api/align/status/${trackId}`);
        if (result.track) onTrackUpdated?.(result.track);
        if (result.error) setError(result.error);
        if (result.status === "ready") {
          window.clearInterval(pollRef.current);
          pollRef.current = null;
          setIsWorking(false);
          setMessage(isPodcast ? "Subtitles ready." : "Lyrics ready.");
          await loadTtml(trackId);
        }
        if (result.status === "needs_review") {
          window.clearInterval(pollRef.current);
          pollRef.current = null;
          setIsWorking(false);
          if (!isPodcast) {
            setShowManual(true);
            setMessage("Add or edit lyrics, then align again.");
          } else {
            setMessage("Transcription failed. Try again.");
          }
        }
      } catch (err) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
        setIsWorking(false);
        setError(err.message);
      }
    }, 2000);
  }

  async function alignWithLyrics(text) {
    if (!track?.id) return;
    setIsWorking(true);
    setError("");
    setMessage("Aligning lyrics...");
    const result = await fetchJson("/api/align", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ track_id: track.id, lyrics_text: text }),
    });
    if (result.track) onTrackUpdated?.(result.track);
    startPolling(track.id);
  }

  function openManualLyrics() {
    setShowManual((value) => !value);
    setError("");
    if (!showManual && !lyricsText) {
      setMessage(ttml ? "Paste corrected lyrics to regenerate sync." : "Paste lyrics, then align this track.");
    }
  }

  async function generateLyrics() {
    if (!track?.id) return;
    setIsWorking(true);
    setError("");
    setMessage("Looking for lyrics...");
    try {
      const result = await fetchJson(`/api/lyrics/fetch?track_id=${track.id}`);
      if (result.lyrics) {
        setLyricsText(result.lyrics);
        setShowManual(true);
        setMessage(`Lyrics found${result.source ? ` from ${result.source}` : ""}. Syncing now...`);
        await alignWithLyrics(result.lyrics);
      } else {
        setShowManual(true);
        setMessage(result.message || "No lyrics found. Paste lyrics below to align this track.");
        setIsWorking(false);
      }
    } catch (err) {
      setShowManual(true);
      setIsWorking(false);
      setError(err.message);
    }
  }

  async function generateSubtitles() {
    if (!track?.id) return;
    setIsWorking(true);
    setError("");
    setMessage("Transcribing audio...");
    try {
      const result = await fetchJson("/api/transcribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ track_id: track.id }),
      });
      if (result.track) onTrackUpdated?.(result.track);
      startPolling(track.id);
    } catch (err) {
      setIsWorking(false);
      setError(err.message);
    }
  }

  async function handleManualSubmit(event) {
    event.preventDefault();
    const text = lyricsText.trim();
    if (!text) {
      setError("Paste lyrics before aligning.");
      return;
    }
    await alignWithLyrics(text);
  }

  async function deleteLyrics() {
    if (!track?.id) return;
    setIsWorking(true);
    setError("");
    try {
      const updated = await fetchJson(`/api/ttml/${track.id}`, {
        method: "DELETE",
      });
      setTtml("");
      setLyricsText("");
      setShowManual(false);
      setMessage("Synced lyrics deleted.");
      onTrackUpdated?.(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsWorking(false);
    }
  }

  function wordProgress(word) {
    if (effectiveTime <= word.start) return 0;
    if (effectiveTime >= word.end) return 1;
    const duration = Math.max(word.end - word.start, 0.001);
    return (effectiveTime - word.start) / duration;
  }

  function renderPhoneticLine(line, isActiveLine) {
    return (
      <p
        key={line.id}
        ref={isActiveLine ? activeRef : null}
        className={`min-h-[2.75rem] transition-all duration-500 ${
          isActiveLine ? "scale-[1.03] opacity-100" : "opacity-55"
        }`}
      >
        {line.words.map((word) => {
          const progress = wordProgress(word);
          const completed = progress >= 1;
          const globalActive = progress > 0 && progress < 1;
          return (
            <span
              key={word.id}
              className="mr-2 inline-block align-baseline transition-transform duration-300 ease-out"
              style={{
                transform: globalActive ? "translateY(-1px) scale(1.035)" : "none",
              }}
            >
              <span
                className="inline-block bg-clip-text text-transparent transition-[background-image,filter] duration-150 ease-linear"
                style={{
                  backgroundImage: `linear-gradient(90deg, #fde68a ${Math.round(
                    progress * 100,
                  )}%, ${completed ? "#fde68a" : "#71717a"} ${Math.round(
                    progress * 100,
                  )}%)`,
                  WebkitBackgroundClip: "text",
                  filter: globalActive ? "drop-shadow(0 0 10px rgba(251, 191, 36, 0.3))" : "none",
                }}
              >
                {word.text}
              </span>
              {showPhonetics && word.phonetic && (
                <span className="mb-1 block text-xs leading-none text-zinc-500">
                  {word.phonetic}
                </span>
              )}
            </span>
          );
        })}
      </p>
    );
  }

  function lyricWordClass(word, isActiveLine) {
    if (word.globalIndex < activeIdx) {
      return "text-amber-200";
    }
    if (word.globalIndex === activeIdx) {
      return "scale-[1.055]";
    }
    return isActiveLine ? "text-zinc-300" : "text-zinc-500";
  }

  function lyricWordStyle(word) {
    const isActiveWord = word.globalIndex === activeIdx;
    if (!isActiveWord) return undefined;
    const progress = Math.round(wordProgress(word) * 1000) / 10;
    return {
      backgroundImage: `linear-gradient(90deg, #fef3c7 ${progress}%, #facc15 ${Math.min(
        progress + 12,
        100,
      )}%, #d4d4d8 ${Math.min(progress + 12, 100)}%)`,
      WebkitBackgroundClip: "text",
      color: "transparent",
      filter: "drop-shadow(0 0 10px rgba(251, 191, 36, 0.45))",
    };
  }

  if (!track) {
    return (
      <section className="min-h-[260px] rounded-md border border-zinc-800 bg-[#171a1d] p-4 text-sm text-zinc-400">
        Select a track to view synced lyrics.
      </section>
    );
  }

  return (
    <section className="flex min-h-[260px] flex-col rounded-md border border-zinc-800 bg-[#171a1d]">
      <div className="flex items-center justify-between gap-3 border-b border-zinc-800 px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <FileText className="h-4 w-4 shrink-0 text-teal-300" aria-hidden="true" />
          <h3 className="truncate text-sm font-semibold text-zinc-100">
            {isPodcast ? "Synced subtitles" : "Synced lyrics"}
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <PhoneticLayer
            hasPhonetics={hasPhonetics}
            showPhonetics={showPhonetics}
            onToggle={() => setShowPhonetics((p) => !p)}
          />
          {!isPodcast && (
            <button
              type="button"
              onClick={openManualLyrics}
              disabled={isWorking}
              className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-zinc-700 bg-[#101214] px-3 text-sm font-medium text-zinc-200 transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <PencilLine className="h-4 w-4" aria-hidden="true" />
              <span>Paste lyrics</span>
            </button>
          )}
          {ttml && (
            <button
              type="button"
              onClick={deleteLyrics}
              disabled={isWorking}
              className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-zinc-700 bg-transparent text-zinc-400 transition hover:bg-rose-500/10 hover:text-rose-200 disabled:cursor-not-allowed disabled:opacity-50"
              title="Delete synced lyrics"
              aria-label="Delete synced lyrics"
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
          <button
            type="button"
            onClick={isPodcast ? generateSubtitles : generateLyrics}
            disabled={isWorking}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-teal-500/40 bg-teal-500/15 px-3 text-sm font-medium text-teal-100 transition hover:bg-teal-500/25 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isWorking ? (
              <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Sparkles className="h-4 w-4" aria-hidden="true" />
            )}
            <span>
              {ttml
                ? "Regenerate"
                : isPodcast
                  ? "Generate subtitles"
                  : "Generate"}
            </span>
          </button>
        </div>
      </div>

      {error && (
        <div className="border-b border-rose-400/30 bg-rose-500/10 px-4 py-2 text-sm text-rose-100">
          {error}
        </div>
      )}
      {message && (
        <div className="border-b border-zinc-800 px-4 py-2 text-sm text-zinc-300">
          {message}
        </div>
      )}

      {ttml && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800 px-4 py-2 text-xs text-zinc-400">
          <span>Timing offset: {timeOffset >= 0 ? "+" : ""}{timeOffset.toFixed(1)}s</span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setTimeOffset((value) => Number((value - 0.1).toFixed(1)))}
              className="flex h-7 w-7 items-center justify-center rounded-md border border-zinc-700 text-zinc-300 transition hover:bg-zinc-800"
              title="Show lyrics earlier"
              aria-label="Show lyrics earlier"
            >
              <Minus className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => setTimeOffset(0)}
              className="flex h-7 w-7 items-center justify-center rounded-md border border-zinc-700 text-zinc-300 transition hover:bg-zinc-800"
              title="Reset lyric timing"
              aria-label="Reset lyric timing"
            >
              <RefreshCcw className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => setTimeOffset((value) => Number((value + 0.1).toFixed(1)))}
              className="flex h-7 w-7 items-center justify-center rounded-md border border-zinc-700 text-zinc-300 transition hover:bg-zinc-800"
              title="Show lyrics later"
              aria-label="Show lyrics later"
            >
              <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        </div>
      )}

      {showManual && !isPodcast && (
        <form onSubmit={handleManualSubmit} className="border-b border-zinc-800 p-4">
          <textarea
            value={lyricsText}
            onChange={(event) => setLyricsText(event.target.value)}
            placeholder="Paste the exact lyrics here. Keep line breaks as you want them displayed."
            className="h-32 w-full resize-none rounded-md border border-zinc-700 bg-[#101214] px-3 py-2 text-sm text-zinc-100 outline-none transition placeholder:text-zinc-600 focus:border-teal-400"
          />
          <div className="mt-3 flex justify-end">
            <button
              type="submit"
              disabled={isWorking}
              className="inline-flex h-9 items-center justify-center rounded-md border border-zinc-700 bg-[#101214] px-3 text-sm font-medium text-zinc-100 transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {ttml ? "Regenerate with pasted lyrics" : "Align lyrics"}
            </button>
          </div>
        </form>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6">
        {lines.length ? (
          <div className="mx-auto max-w-4xl space-y-5 text-center font-semibold leading-[1.65] tracking-normal">
            {lines.map((line) => {
              if (line.kind === "gap") {
                return <div key={line.id} className="h-4" aria-hidden="true" />;
              }

              if (line.kind === "label") {
                return (
                  <p key={line.id} className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-300/60">
                    {line.text}
                  </p>
                );
              }

              const isActiveLine = activeLineIdx === line.lineIndex;
              const isComplete = line.end > 0 && effectiveTime > line.end;

              if (showPhonetics && line.words.some((word) => word.phonetic)) {
                return renderPhoneticLine(line, isActiveLine);
              }

              return (
                <p
                  key={line.id}
                  ref={isActiveLine ? activeRef : null}
                  className={`mx-auto max-w-full px-2 text-[1.55rem] transition-all duration-500 ease-out md:text-[1.95rem] ${
                    isActiveLine
                      ? "scale-[1.035] opacity-100"
                    : isComplete
                        ? "opacity-[0.82]"
                        : "opacity-45"
                  }`}
                >
                  {line.words.map((word) => (
                    <span
                      key={word.id}
                      className={`mr-2 inline-block align-baseline transition-[color,transform,filter] duration-200 ease-out ${lyricWordClass(
                        word,
                        isActiveLine,
                      )}`}
                      style={lyricWordStyle(word)}
                    >
                      {word.text}
                    </span>
                  ))}
                </p>
              );
            })}
          </div>
        ) : (
          <div className="text-sm text-zinc-400">
            {isWorking
              ? isPodcast
                ? "Transcribing audio..."
                : "Preparing synced lyrics..."
              : isPodcast
                ? "No subtitles yet."
                : "No synced lyrics yet."}
          </div>
        )}
      </div>
    </section>
  );
}
