import {
  Album,
  FileAudio,
  FileX2,
  FolderOpen,
  FolderPlus,
  Layers3,
  ListMusic,
  Loader2,
  Music2,
  RefreshCw,
  Search,
  Settings,
  Trash2,
  UserRound,
  X,
} from "../icons.js";
import { useEffect, useMemo, useRef, useState } from "react";

const UNKNOWN_ALBUM = "Unknown Album";
const UNKNOWN_ARTIST = "Unknown Artist";

const browseModes = [
  { id: "albums", label: "Albums", icon: Album },
  { id: "artists", label: "Artists", icon: UserRound },
  { id: "singles", label: "Singles", icon: Music2 },
  { id: "status", label: "Status", icon: Layers3 },
  { id: "all", label: "All", icon: ListMusic },
];

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
  if (status === "needs_review") return "border-rose-400/40 bg-rose-400/10 text-rose-200";
  if (status === "aligning" || status === "fetching_lyrics") return "border-sky-400/40 bg-sky-400/10 text-sky-200";
  return "border-zinc-500/40 bg-zinc-500/10 text-zinc-300";
}

function clean(value, fallback) {
  const text = String(value || "").trim();
  return text || fallback;
}

function normalize(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function isSingle(track) {
  const album = clean(track.album, "");
  if (!album || album === UNKNOWN_ALBUM) return true;
  return normalize(album) === normalize(track.title);
}

function trackMatches(track, query) {
  if (!query) return true;
  const haystack = [
    track.title,
    track.artist,
    track.album,
    track.status,
    track.type,
    track.path,
  ]
    .map((part) => String(part || "").toLowerCase())
    .join(" ");
  return haystack.includes(query.toLowerCase());
}

function sortTracks(a, b) {
  return (
    clean(a.artist, UNKNOWN_ARTIST).localeCompare(clean(b.artist, UNKNOWN_ARTIST)) ||
    clean(a.album, UNKNOWN_ALBUM).localeCompare(clean(b.album, UNKNOWN_ALBUM)) ||
    clean(a.title, "Untitled").localeCompare(clean(b.title, "Untitled"))
  );
}

function groupTracks(tracks, mode) {
  if (mode === "all") {
    return [{ key: "all", title: "All songs", subtitle: `${tracks.length} tracks`, tracks: [...tracks].sort(sortTracks) }];
  }

  const visibleTracks = mode === "singles" ? tracks.filter(isSingle) : tracks;
  const groups = new Map();

  visibleTracks.forEach((track) => {
    let title = "Songs";
    let subtitle = "";

    if (mode === "albums") {
      title = isSingle(track) ? "Singles and loose files" : clean(track.album, UNKNOWN_ALBUM);
      subtitle = clean(track.artist, UNKNOWN_ARTIST);
    } else if (mode === "artists") {
      title = clean(track.artist, UNKNOWN_ARTIST);
      subtitle = clean(track.album, UNKNOWN_ALBUM);
    } else if (mode === "singles") {
      title = clean(track.artist, UNKNOWN_ARTIST);
      subtitle = "Singles and files without album metadata";
    } else if (mode === "status") {
      title = clean(track.status, "unprocessed");
      subtitle = "Processing state";
    }

    const key = `${mode}:${normalize(title) || title}`;
    if (!groups.has(key)) {
      groups.set(key, { key, title, subtitle, tracks: [] });
    }
    groups.get(key).tracks.push(track);
  });

  return Array.from(groups.values())
    .map((group) => ({ ...group, tracks: group.tracks.sort(sortTracks) }))
    .sort((a, b) => {
      if (a.title === "Singles and loose files") return 1;
      if (b.title === "Singles and loose files") return -1;
      return a.title.localeCompare(b.title);
    });
}

export default function Library({
  tracks,
  selectedTrackId,
  onSelectTrack,
  onImported,
  onUploadFiles,
  onDeleteTrack,
  onDeleteTrackAndFile,
  onSetType,
  onOpenSettings,
  isLoading,
  isLibraryLoading,
}) {
  const fileInputRef = useRef(null);
  const folderInputRef = useRef(null);
  const [query, setQuery] = useState("");
  const [browseMode, setBrowseMode] = useState("albums");

  useEffect(() => {
    if (!folderInputRef.current) return;
    folderInputRef.current.setAttribute("webkitdirectory", "");
    folderInputRef.current.setAttribute("directory", "");
  }, []);

  const filteredTracks = useMemo(
    () => tracks.filter((track) => trackMatches(track, query)),
    [tracks, query],
  );
  const groupedTracks = useMemo(
    () => groupTracks(filteredTracks, browseMode),
    [filteredTracks, browseMode],
  );
  const albumCount = useMemo(
    () => new Set(tracks.filter((track) => !isSingle(track)).map((track) => normalize(track.album))).size,
    [tracks],
  );

  async function handleSubmit(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const path = String(form.get("path") || "").trim();
    if (!path) return;
    await onImported(path);
    event.currentTarget.reset();
  }

  async function handleFileChange(event) {
    const files = Array.from(event.currentTarget.files || []);
    event.currentTarget.value = "";
    if (files.length === 0) return;
    await onUploadFiles(files);
  }

  function renderTrackRow(track) {
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
        className={`grid w-full cursor-pointer grid-cols-[42px_minmax(0,1fr)_auto] gap-3 px-3 py-2.5 text-left transition ${
          selected ? "bg-teal-500/15 ring-1 ring-inset ring-teal-400/30" : "hover:bg-zinc-800/70"
        }`}
      >
        <div className="flex h-10 w-10 items-center justify-center overflow-hidden rounded-md bg-[#24282d]">
          {track.cover_art ? (
            <img src={track.cover_art} alt="" className="h-full w-full object-cover" />
          ) : (
            <Music2 className="h-4 w-4 text-zinc-500" aria-hidden="true" />
          )}
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-zinc-100">
            {track.title || "Untitled"}
          </div>
          <div className="mt-0.5 truncate text-xs text-zinc-400">
            {clean(track.artist, UNKNOWN_ARTIST)}
          </div>
          <div className="mt-0.5 truncate text-xs text-zinc-500">
            {clean(track.album, UNKNOWN_ALBUM)}
          </div>
        </div>
        <div className="flex min-w-[94px] flex-col items-end gap-1.5">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onSetType?.(track.id, track.type === "podcast" ? "music" : "podcast");
              }}
              className="rounded-md border border-zinc-700 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400 transition hover:bg-zinc-800 hover:text-zinc-200"
              title="Toggle music or podcast"
            >
              {track.type === "podcast" ? "Podcast" : "Music"}
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onDeleteTrack?.(track.id);
              }}
              className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-500 transition hover:bg-rose-500/10 hover:text-rose-200"
              title="Remove from library (keeps audio file for re-import)"
              aria-label={`Remove ${track.title || "track"} from library`}
            >
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onDeleteTrackAndFile?.(track.id);
              }}
              className="flex h-7 w-7 items-center justify-center rounded-md border border-rose-500/30 text-rose-300/80 transition hover:bg-rose-500/15 hover:text-rose-100"
              title="Delete track and audio file from disk"
              aria-label={`Delete ${track.title || "track"} and its audio file`}
            >
              <FileX2 className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
          <span className="text-xs tabular-nums text-zinc-500">
            {formatDuration(track.duration)}
          </span>
          <span className={`rounded-md border px-2 py-0.5 text-[11px] ${statusClass(track.status)}`}>
            {track.status || "unprocessed"}
          </span>
        </div>
      </div>
    );
  }

  return (
    <aside className="flex min-h-0 flex-col border-r border-zinc-800 bg-[#15181b]">
      <div className="border-b border-zinc-800 px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold tracking-normal text-zinc-50">Verbatone</h1>
            <p className="text-xs text-zinc-400">
              {tracks.length} tracks · {albumCount} albums
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onOpenSettings}
              className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-400 transition hover:bg-zinc-800 hover:text-zinc-200"
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
            {isLoading ? <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" /> : <FileAudio className="h-4 w-4" aria-hidden="true" />}
            <span>Files</span>
          </button>
          <button
            type="button"
            disabled={isLoading}
            onClick={() => folderInputRef.current?.click()}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-teal-500/40 bg-teal-500/15 px-3 text-sm font-medium text-teal-100 transition hover:bg-teal-500/25 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoading ? <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" /> : <FolderOpen className="h-4 w-4" aria-hidden="true" />}
            <span>Folder</span>
          </button>
        </div>

        <div className="relative mt-3">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" aria-hidden="true" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search title, artist, album"
            className="h-10 w-full rounded-md border border-zinc-700 bg-[#101214] pl-9 pr-9 text-sm text-zinc-100 outline-none transition placeholder:text-zinc-600 focus:border-teal-400"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-zinc-500 transition hover:bg-zinc-800 hover:text-zinc-200"
              title="Clear search"
              aria-label="Clear search"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          )}
        </div>

        <div className="mt-3 grid grid-cols-5 gap-1 rounded-md border border-zinc-800 bg-[#101214] p-1">
          {browseModes.map((mode) => {
            const Icon = mode.icon;
            const selected = browseMode === mode.id;
            return (
              <button
                key={mode.id}
                type="button"
                onClick={() => setBrowseMode(mode.id)}
                className={`flex h-8 items-center justify-center rounded-md transition ${
                  selected ? "bg-zinc-700 text-zinc-50" : "text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
                }`}
                title={mode.label}
                aria-label={mode.label}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            );
          })}
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
        ) : filteredTracks.length === 0 ? (
          <div className="px-4 py-8 text-sm text-zinc-400">
            No songs match this search.
          </div>
        ) : (
          <div className="pb-3">
            {groupedTracks.map((group) => (
              <section key={group.key} className="border-b border-zinc-800/80">
                <div className="sticky top-0 z-[1] border-b border-zinc-800 bg-[#15181b]/95 px-3 py-2 backdrop-blur">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <h2 className="truncate text-xs font-semibold uppercase tracking-wide text-zinc-300">
                        {group.title}
                      </h2>
                      <p className="truncate text-[11px] text-zinc-500">
                        {group.subtitle}
                      </p>
                    </div>
                    <span className="rounded-md border border-zinc-700 px-2 py-0.5 text-[11px] text-zinc-400">
                      {group.tracks.length}
                    </span>
                  </div>
                </div>
                <div className="divide-y divide-zinc-800/70">
                  {group.tracks.map(renderTrackRow)}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
