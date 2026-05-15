import { useCallback, useEffect, useRef, useState } from "react";

export function useAudioSync(audioRef) {
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const frameRef = useRef(null);

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
      setCurrentTime(audio.currentTime || 0);
      frameRef.current = audio.paused ? null : window.requestAnimationFrame(tick);
    };
    const startFrameLoop = () => {
      stopFrameLoop();
      frameRef.current = window.requestAnimationFrame(tick);
    };
    const markPlaying = () => {
      setIsPlaying(true);
      startFrameLoop();
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
