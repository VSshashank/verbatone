import { FileAudio, FolderOpen, FolderPlus, Loader2, Music2, RefreshCw, Settings, Trash2 } from "lucide-react";
import { useEffect, useRef } from "react";

function formatDuration(seconds) {
  if (!seconds) return "--:--";
  const total = Math.round(seconds);
  const mins = Math.floor(total / 60);
  const secs = String(total % 60).padStart(2, "0");
  return `${mins}:${secs}`;
}

function statusClass(status) {
  if (status === "ready") return "border-teal-400/40 bg-teal-400/10 text-teal-200";
  if (status === "karaoke_ready") return "border-amber-400/40 bg-amber-400/10 text-amber-200";
  return "border-zinc-500/40 bg-zinc-500/10 text-zinc-300";
}

export default function Library({
  tracks,
  selectedTrackId,
  onSelectTrack,
  onImported,
  onUploadFiles,
  onDeleteTrack,
  onSetType,
  onOpenSettings,
  isLoading,
  isLibraryLoading,
}) {
  const fileInputRef = useRef(null);
  const folderInputRef = useRef(null);

  useEffect(() => {
    if (!folderInputRef.current) return;
    folderInputRef.current.setAttribute("webkitdirectory", "");
    folderInputRef.current.setAttribute("directory", "");
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const path = String(form.get("path") || "").trim();
    if (!path) return;
    await onImported(path);
  }

  async function handleFileChange(event) {
    const files = Array.from(event.currentTarget.files || []);
    event.currentTarget.value = "";
    if (files.length === 0) return;
    await onUploadFiles(files);
  }

  return (
    <aside className="flex min-h-0 flex-col border-r border-zinc-800 bg-[#171a1d]">
      <div className="border-b border-zinc-800 px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold tracking-normal text-zinc-50">Verbatone</h1>
            <p className="text-xs text-zinc-400">Local library</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onOpenSettings}
              className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 transition hover:bg-zinc-800 hover:text-zinc-200"
              title="Settings"
              aria-label="Settings"
            >
              <Settings className="h-4 w-4" aria-hidden="true" />
            </button>
            <Music2 className="h-5 w-5 text-teal-300" aria-hidden="true" />
          </div>
        </div>
      </div>

      <div className="border-b border-zinc-800 p-3">
        <input
          ref={fileInputRef}
          type="file"
          accept="audio/*,.mp3,.flac,.wav,.m4a,.aac,.ogg"
          multiple
          onChange={handleFileChange}
          className="hidden"
        />
        <input
          ref={folderInputRef}
          type="file"
          accept="audio/*,.mp3,.flac,.wav,.m4a,.aac,.ogg"
          multiple
          onChange={handleFileChange}
          className="hidden"
        />

        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            disabled={isLoading}
            onClick={() => fileInputRef.current?.click()}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-teal-500/40 bg-teal-500/15 px-3 text-sm font-medium text-teal-100 transition hover:bg-teal-500/25 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoading ? (
              <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <FileAudio className="h-4 w-4" aria-hidden="true" />
            )}
            <span>Choose files</span>
          </button>
          <button
            type="button"
            disabled={isLoading}
            onClick={() => folderInputRef.current?.click()}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-teal-500/40 bg-teal-500/15 px-3 text-sm font-medium text-teal-100 transition hover:bg-teal-500/25 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoading ? (
              <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <FolderOpen className="h-4 w-4" aria-hidden="true" />
            )}
            <span>Choose folder</span>
          </button>
        </div>

        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-medium text-zinc-400">
            Import by path
          </summary>
          <form onSubmit={handleSubmit} className="mt-2 flex gap-2">
            <input
              id="import-path"
              name="path"
              placeholder="/Users/you/Music"
              className="min-w-0 flex-1 rounded-md border border-zinc-700 bg-[#101214] px-3 py-2 text-sm text-zinc-100 outline-none transition focus:border-teal-400"
            />
            <button
              type="submit"
              disabled={isLoading}
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-zinc-700 bg-[#101214] text-zinc-200 transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
              title="Import path"
              aria-label="Import path"
            >
              <FolderPlus className="h-4 w-4" aria-hidden="true" />
            </button>
          </form>
        </details>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {isLibraryLoading ? (
          <div className="flex flex-col items-center justify-center gap-3 px-4 py-12">
            <Loader2 className="h-6 w-6 animate-spin text-teal-300" aria-hidden="true" />
            <p className="text-sm text-zinc-400">Loading library…</p>
          </div>
        ) : tracks.length === 0 ? (
          <div className="px-4 py-8 text-sm text-zinc-400">
            Choose audio files or a folder to fill the queue.
          </div>
        ) : (
          <div className="divide-y divide-zinc-800">
            {tracks.map((track) => {
              const selected = selectedTrackId === track.id;
              return (
                <div
                  key={track.id}
                  onClick={() => onSelectTrack(track)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelectTrack(track);
                    }
                  }}
                  className={`grid w-full cursor-pointer grid-cols-[48px_minmax(0,1fr)_auto] gap-3 px-3 py-3 text-left transition ${
                    selected ? "bg-teal-500/12" : "hover:bg-zinc-800/70"
                  }`}
                >
                  <div className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-md bg-[#24282d]">
                    {track.cover_art ? (
                      <img
                        src={track.cover_art}
                        alt=""
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <Music2 className="h-5 w-5 text-zinc-500" aria-hidden="true" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-zinc-100">
                      {track.title || "Untitled"}
                    </div>
                    <div className="mt-0.5 truncate text-xs text-zinc-400">
                      {track.artist || "Unknown Artist"}
                    </div>
                    <div className="mt-1 truncate text-xs text-zinc-500">
                      {track.album || "Unknown Album"}
                    </div>
                  </div>
                  <div className="flex min-w-[96px] flex-col items-end gap-2">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteTrack?.(track.id);
                      }}
                      className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-500 transition hover:bg-rose-500/10 hover:text-rose-200"
                      title="Remove from library"
                      aria-label={`Remove ${track.title || "track"} from library`}
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                    <span className="text-xs tabular-nums text-zinc-500">
                      {formatDuration(track.duration)}
                    </span>
                    <span
                      className={`rounded-md border px-2 py-0.5 text-[11px] ${statusClass(
                        track.status,
                      )}`}
                    >
                      {track.status || "unprocessed"}
                    </span>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSetType?.(track.id, track.type === "podcast" ? "music" : "podcast");
                      }}
                      className="text-[11px] text-zinc-500 transition hover:text-zinc-300"
                      title="Toggle music/podcast"
                    >
                      {track.type === "podcast" ? "🎙 Podcast" : "🎵 Music"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );
}
