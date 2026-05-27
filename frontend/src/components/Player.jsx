import { AlertTriangle, Captions, Disc3, Mic2, Pause, Play, SkipBack, SkipForward, Sparkles, Volume2 } from "../icons.js";
import { useEffect, useMemo, useRef, useState } from "react";
import LyricsDisplay from "./LyricsDisplay.jsx";
import KaraokeSolo from "./KaraokeSolo.jsx";
import { useAudioSync } from "../hooks/useAudioSync.js";

function formatTime(seconds) {
  if (!seconds) return "0:00";
  const total = Math.floor(seconds);
  const mins = Math.floor(total / 60);
  const secs = String(total % 60).padStart(2, "0");
  return `${mins}:${secs}`;
}

export default function Player({ track, tracks, onSelectTrack, onTrackUpdated }) {
  const audioRef = useRef(null);
  const [playbackError, setPlaybackError] = useState("");
  const [karaokeOpen, setKaraokeOpen] = useState(false);
  const [useInstrumental, setUseInstrumental] = useState(false);
  const { currentTime, duration, isPlaying, seek } = useAudioSync(audioRef);

  const activeIndex = useMemo(
    () => tracks.findIndex((item) => item.id === track?.id),
    [tracks, track],
  );
  const hasPrevious = activeIndex > 0;
  const hasNext = activeIndex >= 0 && activeIndex < tracks.length - 1;
  const queueLabel = activeIndex >= 0 ? `${activeIndex + 1} of ${tracks.length}` : `${tracks.length} tracks`;

  const audioSrc = track
    ? useInstrumental
      ? `/api/stems/${track.id}/instrumental`
      : `/api/audio/${track.id}`
    : undefined;

  useEffect(() => {
    setPlaybackError("");
    setUseInstrumental(false);
    setKaraokeOpen(false);
  }, [track?.id]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.load();
  }, [audioSrc]);

  async function togglePlay() {
    const audio = audioRef.current;
    if (!audio || !track) return;
    setPlaybackError("");
    try {
      if (audio.paused) {
        await audio.play();
      } else {
        audio.pause();
      }
    } catch (err) {
      setPlaybackError(err.message || "The browser could not start playback.");
    }
  }

  function selectRelative(offset) {
    const next = tracks[activeIndex + offset];
    if (next) onSelectTrack(next);
  }

  function handleEnded() {
    if (hasNext) selectRelative(1);
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col bg-[#101215]">
      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        {track ? (
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-5">
            <div className="relative overflow-hidden rounded-md border border-zinc-800 bg-[#171a1d] shadow-2xl shadow-black/20">
              {track.cover_art && (
                <img
                  src={track.cover_art}
                  alt=""
                  className="pointer-events-none absolute inset-0 h-full w-full scale-110 object-cover opacity-15 blur-2xl"
                />
              )}
              <div className="player-hero-grid relative grid gap-5 p-4">
              <div className="aspect-square overflow-hidden rounded-md bg-[#24282d] shadow-xl shadow-black/30 ring-1 ring-white/5">
                {track.cover_art ? (
                  <img src={track.cover_art} alt="" className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-zinc-500">
                    <Disc3 className="h-12 w-12" aria-hidden="true" />
                  </div>
                )}
              </div>

              <div className="flex min-w-0 flex-col justify-center">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <span className="rounded-md border border-teal-400/30 bg-teal-400/10 px-2 py-1 text-xs font-medium text-teal-100">
                    {useInstrumental ? "Karaoke backing" : "Now playing"}
                  </span>
                  <span className="rounded-md border border-zinc-700 px-2 py-1 text-xs text-zinc-400">
                    {track.status || "unprocessed"}
                  </span>
                  <span className="rounded-md border border-zinc-700 px-2 py-1 text-xs text-zinc-400">
                    Queue {queueLabel}
                  </span>
                  {track.ttml_path && (
                    <span className="inline-flex items-center gap-1 rounded-md border border-sky-400/30 bg-sky-400/10 px-2 py-1 text-xs text-sky-100">
                      <Captions className="h-3.5 w-3.5" aria-hidden="true" />
                      Lyrics ready
                    </span>
                  )}
                  {track.instrumental_path && (
                    <span className="inline-flex items-center gap-1 rounded-md border border-amber-400/30 bg-amber-400/10 px-2 py-1 text-xs text-amber-100">
                      <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                      Karaoke ready
                    </span>
                  )}
                </div>
                <h2 className="text-balance text-3xl font-semibold tracking-normal text-zinc-50 max-md:text-2xl">
                  {track.title || "Untitled"}
                </h2>
                <p className="mt-2 truncate text-base text-zinc-300">
                  {track.artist || "Unknown Artist"}
                </p>
                <p className="mt-1 truncate text-sm text-zinc-500">
                  {track.album || "Unknown Album"}
                </p>
                <div className="mt-6 rounded-md border border-zinc-800 bg-[#101214]/90 p-4 backdrop-blur">
                  <div className="flex items-center justify-between text-xs tabular-nums text-zinc-400">
                    <span>{formatTime(currentTime)}</span>
                    <span>{formatTime(duration || track.duration)}</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max={duration || track.duration || 0}
                    step="0.01"
                    value={Math.min(currentTime, duration || track.duration || 0)}
                    onChange={(event) => seek(Number(event.target.value))}
                    className="mt-3 w-full"
                    aria-label="Seek"
                  />
                </div>
                {playbackError && (
                  <div className="mt-3 flex items-start gap-2 rounded-md border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-100">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                    <span>{playbackError}</span>
                  </div>
                )}
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setKaraokeOpen((value) => !value)}
                    className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-amber-400/40 bg-amber-400/10 px-3 text-sm font-medium text-amber-100 transition hover:bg-amber-400/20"
                  >
                    <Mic2 className="h-4 w-4" aria-hidden="true" />
                    {karaokeOpen ? "Hide karaoke" : "Solo karaoke"}
                  </button>
                </div>
              </div>
              </div>
            </div>
            {karaokeOpen && (
              <KaraokeSolo
                track={track}
                isInstrumental={useInstrumental}
                onUseInstrumental={setUseInstrumental}
                onTrackUpdated={onTrackUpdated}
              />
            )}
            <LyricsDisplay
              track={track}
              currentTime={currentTime}
              onTrackUpdated={onTrackUpdated}
            />
          </div>
        ) : (
          <div className="flex min-h-full items-center justify-center text-center">
            <div>
            <h2 className="text-xl font-semibold tracking-normal text-zinc-100">
              No track selected
            </h2>
            <p className="mt-2 text-sm text-zinc-400">
              Import a folder and choose a song from the library.
            </p>
            </div>
          </div>
        )}
      </div>

      <div className="border-t border-zinc-800 bg-[#15181b]/95 px-4 py-3 backdrop-blur">
        <audio
          ref={audioRef}
          src={audioSrc}
          onEnded={handleEnded}
          onError={() => {
            const audio = audioRef.current;
            const code = audio?.error?.code;
            setPlaybackError(
              code
                ? `Audio could not be loaded by the browser. Error code ${code}.`
                : "Audio could not be loaded by the browser.",
            );
          }}
          preload="metadata"
        />
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-zinc-100">
              {track?.title || "Ready when you are"}
            </div>
            <div className="truncate text-xs text-zinc-500">
              {track ? `${track.artist || "Unknown Artist"} · ${queueLabel}` : "No audio loaded"}
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => selectRelative(-1)}
              disabled={!hasPrevious}
              className="flex h-10 w-10 items-center justify-center rounded-md border border-zinc-700 bg-[#101214] text-zinc-200 transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-35"
              title="Previous"
              aria-label="Previous"
            >
              <SkipBack className="h-4 w-4" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={togglePlay}
              disabled={!track}
              className="flex h-11 w-11 items-center justify-center rounded-md border border-teal-400/60 bg-teal-400/20 text-teal-50 transition hover:bg-teal-400/30 disabled:cursor-not-allowed disabled:opacity-35"
              title={isPlaying ? "Pause" : "Play"}
              aria-label={isPlaying ? "Pause" : "Play"}
            >
              {isPlaying ? (
                <Pause className="h-5 w-5" aria-hidden="true" />
              ) : (
                <Play className="h-5 w-5" aria-hidden="true" />
              )}
            </button>
            <button
              type="button"
              onClick={() => selectRelative(1)}
              disabled={!hasNext}
              className="flex h-10 w-10 items-center justify-center rounded-md border border-zinc-700 bg-[#101214] text-zinc-200 transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-35"
              title="Next"
              aria-label="Next"
            >
              <SkipForward className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>

          <label className="flex min-w-[130px] items-center gap-2 text-zinc-400">
            <Volume2 className="h-4 w-4" aria-hidden="true" />
            <input
              type="range"
              min="0"
              max="1"
              step="0.01"
              defaultValue="1"
              onChange={(event) => {
                if (audioRef.current) audioRef.current.volume = Number(event.target.value);
              }}
              className="w-full"
              aria-label="Volume"
            />
          </label>
        </div>
      </div>
    </section>
  );
}
