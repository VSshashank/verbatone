import { FileText, Minus, PencilLine, Plus, RefreshCcw, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { Fragment, useEffect, useRef, useState } from "react";
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

const DEFAULT_LYRIC_LEAD = 0.3;

export default function LyricsDisplay({ track, currentTime, onTrackUpdated }) {
  const [ttml, setTtml] = useState("");
  const [lyricsText, setLyricsText] = useState("");
  const [showManual, setShowManual] = useState(false);
  const [isWorking, setIsWorking] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [showPhonetics, setShowPhonetics] = useState(false);
  const [timeOffset, setTimeOffset] = useState(DEFAULT_LYRIC_LEAD);
  const activeRef = useRef(null);
  const pollRef = useRef(null);
  const lyricsContainerRef = useRef(null);
  const scrollRafRef = useRef(null);
  const prevActiveLineIdxRef = useRef(-1);
  const lineJustActivatedRef = useRef(false);
  const lineActivationTimerRef = useRef(null);
  const effectiveTime = currentTime + timeOffset;
  const { lines, activeIdx, activeLineIdx, activeWord, hasPhonetics, syncSource } = useTTML(ttml, effectiveTime);
  const isDebugMode = new URLSearchParams(window.location.search).get("debug") === "1";

  const isPodcast = track?.type === "podcast";

  useEffect(() => {
    setTtml("");
    setLyricsText("");
    setShowManual(false);
    setIsWorking(false);
    setMessage("");
    setError("");
    setShowPhonetics(false);
    setTimeOffset(DEFAULT_LYRIC_LEAD);
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
    if (activeLineIdx !== prevActiveLineIdxRef.current) {
      lineJustActivatedRef.current = true;
      prevActiveLineIdxRef.current = activeLineIdx;
      if (lineActivationTimerRef.current) {
        clearTimeout(lineActivationTimerRef.current);
      }
      lineActivationTimerRef.current = setTimeout(() => {
        lineJustActivatedRef.current = false;
        lineActivationTimerRef.current = null;
      }, 380);
    }
    return () => {
      if (lineActivationTimerRef.current) {
        clearTimeout(lineActivationTimerRef.current);
      }
    };
  }, [activeLineIdx]);

  useEffect(() => {
    const container = lyricsContainerRef.current;
    const target = activeRef.current;
    if (!container || !target) return undefined;

    if (scrollRafRef.current) cancelAnimationFrame(scrollRafRef.current);

    const containerHeight = container.clientHeight;
    const targetRect = target.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    const targetTop =
      container.scrollTop +
      (targetRect.top - containerRect.top) -
      containerHeight / 2 +
      targetRect.height / 2;
    const startTop = container.scrollTop;
    const diff = targetTop - startTop;

    if (Math.abs(diff) < 8) return undefined;

    const duration = 380;
    const startTime = performance.now();
    const ease = (t) => (t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t);

    const step = (now) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      container.scrollTop = startTop + diff * ease(progress);
      if (progress < 1) {
        scrollRafRef.current = requestAnimationFrame(step);
      } else {
        scrollRafRef.current = null;
      }
    };

    scrollRafRef.current = requestAnimationFrame(step);

    return () => {
      if (scrollRafRef.current) cancelAnimationFrame(scrollRafRef.current);
    };
  }, [activeLineIdx]);

  async function loadTtml(trackId) {
    try {
      const response = await fetch(
        `/api/ttml/${trackId}?t=${Date.now()}`,
        { cache: "no-store" },
      );
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
        const jobStatus = result.status || result.track?.status;
        if (jobStatus === "aligning" || jobStatus === "fetching_lyrics") {
          setTtml("");
        }
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
    setTtml("");
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
    setTtml("");
    setIsWorking(true);
    setError("");
    setMessage("Looking for lyrics...");
    try {
      const result = await fetchJson(`/api/lyrics/fetch?track_id=${track.id}`);
      // LRCLIB returned perfect sync — alignment already started in background
      if (result.status === "lrclib_synced") {
        setMessage("✦ Perfect sync found — applying now...");
        startPolling(track.id);
        return;
      }
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
    setTtml("");
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
    const start = word.visualStart ?? word.start;
    const end = word.visualEnd ?? word.end;
    if (effectiveTime <= start) return 0;
    if (effectiveTime >= end) return 1;
    const duration = Math.max(end - start, 0.001);
    return (effectiveTime - start) / duration;
  }

  function getWordState(word) {
    const start = word.visualStart ?? word.start;
    const end = word.visualEnd ?? word.end;
    if (effectiveTime >= start && effectiveTime < end) return "active";
    if (effectiveTime >= end && effectiveTime - end < 0.5) return "recent";
    if (effectiveTime < start) return "upcoming";
    return "past";
  }

  function lyricLineClassName(isActiveLine, isComplete) {
    return `mx-auto max-w-full px-2 text-[1.55rem] will-change-[opacity,transform] transition-[opacity,transform] duration-[350ms] ease-[cubic-bezier(0.25,0.1,0.25,1)] md:text-[1.95rem] ${isActiveLine
      ? "scale-[1.02] opacity-100"
      : isComplete
        ? "scale-[1.0] opacity-[0.72]"
        : "scale-[1.0] opacity-30"
      }`;
  }

  function lyricWordPresentation(word, isActiveLine, lineJustActivated) {
    const state = getWordState(word);
    const isActiveWord = state === "active";
    const isRapWord = (word.end - word.start) < 0.3;
    const baseTransition = "transition-[opacity,background-image,transform,filter] duration-[80ms] ease-out";

    let opacity = 0.35;
    if (isActiveLine) {
      if (state === "active") opacity = 1.0;
      else if (state === "recent") opacity = 0.7;
      else opacity = 0.65;
    } else if (state === "active") {
      opacity = 1.0;
    } else if (state === "recent") {
      opacity = 0.7;
    } else if (state === "upcoming") {
      opacity = 0.5;
    }

    const style = {
      opacity,
      transition: "background-image 80ms ease-out, opacity 60ms ease-out, transform 80ms ease-out, filter 80ms ease-out",
    };

    if (isActiveWord) {
      const progress = Math.round(wordProgress(word) * 1000) / 10;
      style.backgroundImage = `linear-gradient(90deg, #fef3c7 ${progress}%, #facc15 ${Math.min(
        progress + 12,
        100,
      )}%, #d4d4d8 ${Math.min(progress + 12, 100)}%)`;
      style.WebkitBackgroundClip = "text";
      style.color = "transparent";
      style.filter = "drop-shadow(0 0 10px rgba(251, 191, 36, 0.45))";
      if (isRapWord && !lineJustActivated) {
        style.animation = "wordPop 80ms ease-out";
      }
    }

    let className = `mr-2 inline-block align-baseline ${baseTransition} `;
    if (isActiveWord) {
      className += "scale-[1.055] ";
    } else if (isActiveLine) {
      className += "text-zinc-300 ";
    } else {
      className += "text-zinc-500 ";
    }

    return { className: className.trim(), style };
  }

  function syncLabel() {
    if (timeOffset === 0) return "Lyrics at audio time";
    if (timeOffset > 0) return `Lyrics ${timeOffset.toFixed(1)}s early`;
    return `Lyrics ${Math.abs(timeOffset).toFixed(1)}s late`;
  }

  function renderPhoneticLine(line, isActiveLine) {
    const isComplete = line.end > 0 && effectiveTime > line.end;
    return (
      <p
        key={line.id}
        ref={isActiveLine ? activeRef : null}
        className={`min-h-[2.75rem] will-change-[opacity,transform] transition-[opacity,transform] duration-[350ms] ease-[cubic-bezier(0.25,0.1,0.25,1)] ${isActiveLine
          ? "scale-[1.02] opacity-100"
          : isComplete
            ? "scale-[1.0] opacity-[0.72]"
            : "scale-[1.0] opacity-30"
          }`}
      >
        {line.words.map((word) => {
          const progress = wordProgress(word);
          const completed = progress >= 1;
          const globalActive = progress > 0 && progress < 1;
          return (
            <Fragment key={word.id}>
              <span
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
              {" "}
            </Fragment>
          );
        })}
      </p>
    );
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
      <style>{`
        @keyframes wordPop {
          0% { transform: scale(1); }
          30% { transform: scale(1.04); }
          100% { transform: scale(1); }
        }
      `}</style>
      {isDebugMode && (
        <div
          id="verbatone-debug-hud"
          style={{
            position: "fixed",
            bottom: "12px",
            right: "12px",
            zIndex: 9999,
            background: "rgba(0,0,0,0.88)",
            border: "1px solid #3f6212",
            borderRadius: "8px",
            padding: "10px 14px",
            fontFamily: "monospace",
            fontSize: "11px",
            lineHeight: "1.7",
            color: "#d9f99d",
            maxWidth: "320px",
            pointerEvents: "none",
          }}
        >
          <div style={{ color: "#86efac", fontWeight: "bold", marginBottom: "4px" }}>🎵 Verbatone Debug HUD</div>
          <div><span style={{ color: "#94a3b8" }}>currentTime     </span>{currentTime.toFixed(3)}s</div>
          <div><span style={{ color: "#94a3b8" }}>effectiveTime   </span>{effectiveTime.toFixed(3)}s</div>
          <div><span style={{ color: "#94a3b8" }}>timeOffset      </span>{timeOffset.toFixed(3)}s</div>
          <hr style={{ border: "none", borderTop: "1px solid #374151", margin: "4px 0" }} />
          {activeWord ? (
            <>
              <div><span style={{ color: "#94a3b8" }}>activeWord.text </span><span style={{ color: "#fde68a" }}>{activeWord.text}</span></div>
              <div><span style={{ color: "#94a3b8" }}>activeWord.start</span>{activeWord.start.toFixed(3)}s</div>
              <div><span style={{ color: "#94a3b8" }}>activeWord.end  </span>{activeWord.end.toFixed(3)}s</div>
              <div>
                <span style={{ color: "#94a3b8" }}>delta (eff-start)</span>
                <span style={{ color: Math.abs(effectiveTime - activeWord.start) > 1.5 ? "#f87171" : "#86efac" }}>
                  {(effectiveTime - activeWord.start).toFixed(3)}s
                </span>
              </div>
            </>
          ) : (
            <div style={{ color: "#6b7280" }}>no active word</div>
          )}
          <hr style={{ border: "none", borderTop: "1px solid #374151", margin: "4px 0" }} />
          <div><span style={{ color: "#94a3b8" }}>totalWords      </span>{lines.flatMap(l => l.words ?? []).length}</div>
        </div>
      )}

      <div className="flex items-center justify-between gap-3 border-b border-zinc-800 px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <FileText className="h-4 w-4 shrink-0 text-teal-300" aria-hidden="true" />
          <h3 className="truncate text-sm font-semibold text-zinc-100">
            {isPodcast ? "Synced subtitles" : "Synced lyrics"}
          </h3>
          {(syncSource === "lrclib" || syncSource === "genius+lrclib") && (
            <span
              title="Timestamps from LRCLIB — sample-accurate line sync"
              className="inline-flex items-center gap-1 rounded-full bg-teal-500/20 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-teal-300 ring-1 ring-inset ring-teal-500/30"
            >
              ✦ Synced
            </span>
          )}
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
          <span>{syncLabel()}</span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setTimeOffset((value) => Number((value + 0.1).toFixed(1)))}
              className="flex h-7 w-7 items-center justify-center rounded-md border border-zinc-700 text-zinc-300 transition hover:bg-zinc-800"
              title="Show lyrics earlier"
              aria-label="Show lyrics earlier"
            >
              <Minus className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => setTimeOffset(DEFAULT_LYRIC_LEAD)}
              className="flex h-7 w-7 items-center justify-center rounded-md border border-zinc-700 text-zinc-300 transition hover:bg-zinc-800"
              title="Reset lyric timing lead"
              aria-label="Reset lyric timing lead"
            >
              <RefreshCcw className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => setTimeOffset((value) => Number((value - 0.1).toFixed(1)))}
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

      <div ref={lyricsContainerRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-6">
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
                  className={lyricLineClassName(isActiveLine, isComplete)}
                >
                  {line.words.map((word) => {
                    const presentation = lyricWordPresentation(
                      word,
                      isActiveLine,
                      lineJustActivatedRef.current,
                    );
                    return (
                    <Fragment key={word.id}>
                      <span
                        className={presentation.className}
                        style={presentation.style}
                      >
                        {word.text}
                      </span>
                      {" "}
                    </Fragment>
                    );
                  })}
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