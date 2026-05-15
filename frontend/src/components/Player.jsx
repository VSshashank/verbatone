import { Pause, Play, SkipBack, SkipForward, Volume2 } from "lucide-react";
import { useMemo, useRef } from "react";
import LyricsDisplay from "./LyricsDisplay.jsx";
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
  const { currentTime, duration, isPlaying, seek } = useAudioSync(audioRef);

  const activeIndex = useMemo(
    () => tracks.findIndex((item) => item.id === track?.id),
    [tracks, track],
  );
  const hasPrevious = activeIndex > 0;
  const hasNext = activeIndex >= 0 && activeIndex < tracks.length - 1;

  // Removed: explicit audio.load() on track change.
  // React's src update already triggers a natural load — calling load()
  // again caused a duplicate network request for every track switch.

  async function togglePlay() {
    const audio = audioRef.current;
    if (!audio || !track) return;
    if (audio.paused) {
      await audio.play();
    } else {
      audio.pause();
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
    <section className="flex min-h-0 flex-1 flex-col bg-[#121417]">
      <div className="min-h-0 flex-1 overflow-y-auto p-6">
        {track ? (
          <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
            <div className="grid grid-cols-[minmax(180px,260px)_minmax(0,1fr)] gap-6 max-md:grid-cols-1">
              <div className="aspect-square overflow-hidden rounded-md bg-[#24282d]">
                {track.cover_art ? (
                  <img src={track.cover_art} alt="" className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-zinc-500">
                    No cover art
                  </div>
                )}
              </div>

              <div className="flex min-w-0 flex-col justify-center">
                <p className="mb-2 text-xs uppercase tracking-normal text-teal-300">
                  Now playing
                </p>
                <h2 className="truncate text-3xl font-semibold tracking-normal text-zinc-50 max-md:text-2xl">
                  {track.title || "Untitled"}
                </h2>
                <p className="mt-2 truncate text-base text-zinc-300">
                  {track.artist || "Unknown Artist"}
                </p>
                <p className="mt-1 truncate text-sm text-zinc-500">
                  {track.album || "Unknown Album"}
                </p>
                <div className="mt-6 rounded-md border border-zinc-800 bg-[#171a1d] p-4">
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
              </div>
            </div>
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

      <div className="border-t border-zinc-800 bg-[#171a1d] px-4 py-3">
        <audio
          ref={audioRef}
          src={track ? `/api/audio/${track.id}` : undefined}
          onEnded={handleEnded}
          preload="metadata"
        />
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-zinc-100">
              {track?.title || "Ready when you are"}
            </div>
            <div className="truncate text-xs text-zinc-500">
              {track?.path || "No audio loaded"}
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
