import { useCallback, useEffect, useRef, useState } from "react";

export function useAudioSync(audioRef) {
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const frameRef = useRef(null);
  const driftRef = useRef(null); // { audioTimeAtStart, wallTimeAtStart, lastLogAt }

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return undefined;

    const updateTime = () => setCurrentTime(audio.currentTime || 0);
    const updateDuration = () => {
      setDuration(Number.isFinite(audio.duration) ? audio.duration : 0);
    };
    const stopFrameLoop = () => {
      if (frameRef.current) {
        window.cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
    };
    const tick = () => {
      const ct = audio.currentTime || 0;
      setCurrentTime(ct);

      // Drift check every 10 seconds of wall-clock time
      if (driftRef.current && !audio.paused) {
        const now = Date.now();
        if (now - driftRef.current.lastLogAt >= 10_000) {
          const wallElapsed = (now - driftRef.current.wallTimeAtStart) / 1000;
          const audioElapsed = ct - driftRef.current.audioTimeAtStart;
          const drift = audioElapsed - wallElapsed;
          const driftSign = drift >= 0 ? "+" : "";
          console.log(
            `[AudioSync] DRIFT CHECK  audio.currentTime=${ct.toFixed(3)}s` +
            `  wallElapsed=${wallElapsed.toFixed(2)}s  audioElapsed=${audioElapsed.toFixed(2)}s` +
            `  drift=${driftSign}${drift.toFixed(3)}s` +
            (Math.abs(drift) > 0.2 ? "  ⚠️ SIGNIFICANT DRIFT" : "  ✅ OK")
          );
          driftRef.current.lastLogAt = now;
        }
      }

      frameRef.current = audio.paused ? null : window.requestAnimationFrame(tick);
    };
    const startFrameLoop = () => {
      stopFrameLoop();
      frameRef.current = window.requestAnimationFrame(tick);
    };
    const markPlaying = () => {
      setIsPlaying(true);
      startFrameLoop();
      // Drift baseline — record audio time and wall-clock time at play start
      driftRef.current = {
        audioTimeAtStart: audio.currentTime,
        wallTimeAtStart: Date.now(),
        lastLogAt: Date.now(),
      };
      console.log(
        `[AudioSync] PLAY  audio.currentTime=${audio.currentTime.toFixed(3)}  wall=${Date.now()}`
      );
    };
    const markPaused = () => {
      setIsPlaying(false);
      updateTime();
      stopFrameLoop();
    };

    audio.addEventListener("timeupdate", updateTime);
    audio.addEventListener("loadedmetadata", updateDuration);
    audio.addEventListener("durationchange", updateDuration);
    audio.addEventListener("play", markPlaying);
    audio.addEventListener("pause", markPaused);
    audio.addEventListener("ended", markPaused);

    updateTime();
    updateDuration();

    return () => {
      audio.removeEventListener("timeupdate", updateTime);
      audio.removeEventListener("loadedmetadata", updateDuration);
      audio.removeEventListener("durationchange", updateDuration);
      audio.removeEventListener("play", markPlaying);
      audio.removeEventListener("pause", markPaused);
      audio.removeEventListener("ended", markPaused);
      stopFrameLoop();
    };
  }, [audioRef]);

  const seek = useCallback(
    (time) => {
      const audio = audioRef.current;
      if (!audio) return;
      const nextTime = Math.max(0, Math.min(time, duration || time));
      audio.currentTime = nextTime;
      setCurrentTime(nextTime);
    },
    [audioRef, duration],
  );

  return { currentTime, duration, isPlaying, seek };
}
