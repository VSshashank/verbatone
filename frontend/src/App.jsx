import { useEffect, useMemo, useState } from "react";
import Library from "./components/Library.jsx";
import Player from "./components/Player.jsx";

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.error || `Request failed: ${response.status}`);
  }
  return data;
}

function SettingsPanel({ onClose }) {
  const [geniusToken, setGeniusToken] = useState("");
  const [musixmatchKey, setMusixmatchKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    setError("");
    try {
      const payload = {};
      if (geniusToken.trim()) payload.genius_token = geniusToken.trim();
      if (musixmatchKey.trim()) payload.musixmatch_key = musixmatchKey.trim();
      await fetchJson("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setSaved(true);
      setGeniusToken("");
      setMusixmatchKey("");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-lg border border-zinc-700 bg-[#171a1d] p-6 shadow-2xl">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-zinc-100">Settings</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-zinc-400 transition hover:text-zinc-200"
          >
            ✕
          </button>
        </div>
        <p className="mt-1 text-xs text-zinc-400">
          API keys are stored locally in SQLite. For Genius, paste the Client Access Token, not the Client ID or secret.
        </p>

        <div className="mt-5 space-y-4">
          <div>
            <label className="block text-sm font-medium text-zinc-300" htmlFor="genius-token">
              Genius Client Access Token
            </label>
            <input
              id="genius-token"
              type="password"
              value={geniusToken}
              onChange={(e) => setGeniusToken(e.target.value)}
              placeholder="Paste token…"
              className="mt-1 w-full rounded-md border border-zinc-700 bg-[#101214] px-3 py-2 text-sm text-zinc-100 outline-none transition placeholder:text-zinc-600 focus:border-teal-400"
            />
            <a
              href="https://genius.com/api-clients"
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-block text-xs text-teal-400 hover:underline"
            >
              Get a free Genius token →
            </a>
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-300" htmlFor="musixmatch-key">
              Musixmatch API Key
            </label>
            <input
              id="musixmatch-key"
              type="password"
              value={musixmatchKey}
              onChange={(e) => setMusixmatchKey(e.target.value)}
              placeholder="Paste key…"
              className="mt-1 w-full rounded-md border border-zinc-700 bg-[#101214] px-3 py-2 text-sm text-zinc-100 outline-none transition placeholder:text-zinc-600 focus:border-teal-400"
            />
          </div>
        </div>

        <div className="mt-6 flex items-center justify-between">
          {saved && (
            <span className="text-sm text-teal-300">Saved ✓</span>
          )}
          {error && (
            <span className="text-sm text-rose-300">{error}</span>
          )}
          {!saved && !error && <span />}
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || (!geniusToken && !musixmatchKey)}
            className="inline-flex h-9 items-center justify-center rounded-md border border-teal-500/40 bg-teal-500/15 px-4 text-sm font-medium text-teal-100 transition hover:bg-teal-500/25 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [tracks, setTracks] = useState([]);
  const [selectedTrackId, setSelectedTrackId] = useState(null);
  const [isImporting, setIsImporting] = useState(false);
  const [isLibraryLoading, setIsLibraryLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [hasApiKeys, setHasApiKeys] = useState(true); // assume true until checked

  const selectedTrack = useMemo(
    () => tracks.find((track) => track.id === selectedTrackId) || null,
    [tracks, selectedTrackId],
  );

  async function loadLibrary() {
    setIsLibraryLoading(true);
    try {
      const library = await fetchJson("/api/library");
      setTracks(library);
      setSelectedTrackId((current) => current || library[0]?.id || null);
    } finally {
      setIsLibraryLoading(false);
    }
  }

  async function checkApiKeys() {
    try {
      const settings = await fetchJson("/api/settings");
      setHasApiKeys(settings.genius_token || settings.musixmatch_key);
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    loadLibrary().catch((err) => {
      setError(err.message);
    });
    checkApiKeys();
  }, []);

  async function importPath(path) {
    setIsImporting(true);
    setError("");
    setNotice("");
    try {
      const result = await fetchJson("/api/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      await loadLibrary();
      setNotice(
        `Imported ${result.imported.length}; skipped ${result.skipped.length}; errors ${result.errors.length}.`,
      );
      if (result.errors.length) {
        setError(result.errors.map((item) => `${item.path}: ${item.error}`).join("\n"));
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsImporting(false);
    }
  }

  async function uploadFiles(files) {
    setIsImporting(true);
    setError("");
    setNotice("");
    try {
      const formData = new FormData();
      for (const file of files) {
        formData.append("files", file, file.webkitRelativePath || file.name);
      }
      const result = await fetchJson("/api/import-upload", {
        method: "POST",
        body: formData,
      });
      await loadLibrary();
      setNotice(
        `Imported ${result.imported.length}; skipped ${result.skipped.length}; errors ${result.errors.length}.`,
      );
      if (result.errors.length) {
        setError(result.errors.map((item) => `${item.path}: ${item.error}`).join("\n"));
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsImporting(false);
    }
  }

  function updateTrack(updatedTrack) {
    setTracks((currentTracks) =>
      currentTracks.map((track) => (track.id === updatedTrack.id ? updatedTrack : track)),
    );
  }

  async function setTrackType(trackId, type) {
    try {
      const updated = await fetchJson(`/api/track/${trackId}/type`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type }),
      });
      updateTrack(updated);
    } catch (err) {
      setError(err.message);
    }
  }

  async function deleteTrack(trackId) {
    const track = tracks.find((item) => item.id === trackId);
    if (!track) return;
    const confirmed = window.confirm(`Remove "${track.title || "this track"}" from Verbatone?`);
    if (!confirmed) return;

    try {
      await fetchJson(`/api/track/${trackId}`, { method: "DELETE" });
      setTracks((currentTracks) => {
        const nextTracks = currentTracks.filter((item) => item.id !== trackId);
        if (selectedTrackId === trackId) {
          setSelectedTrackId(nextTracks[0]?.id || null);
        }
        return nextTracks;
      });
      setNotice("Track removed from library.");
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main className="grid h-screen grid-cols-[minmax(320px,420px)_minmax(0,1fr)] overflow-hidden bg-[#121417] text-zinc-100 max-lg:grid-cols-1 max-lg:grid-rows-[45vh_55vh]">
      <Library
        tracks={tracks}
        selectedTrackId={selectedTrackId}
        onSelectTrack={(track) => setSelectedTrackId(track.id)}
        onImported={importPath}
        onUploadFiles={uploadFiles}
        onDeleteTrack={deleteTrack}
        onSetType={setTrackType}
        onOpenSettings={() => setSettingsOpen(true)}
        isLoading={isImporting}
        isLibraryLoading={isLibraryLoading}
      />
      <div className="relative flex min-h-0 flex-col">
        {!hasApiKeys && (
          <div className="border-b border-amber-400/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-100">
            Add your Genius API key in{" "}
            <button
              type="button"
              onClick={() => setSettingsOpen(true)}
              className="underline"
            >
              Settings
            </button>{" "}
            to enable auto lyrics fetching.
          </div>
        )}
        {(notice || error) && (
          <div className="absolute left-4 right-4 top-4 z-10 space-y-2">
            {notice && (
              <div className="rounded-md border border-teal-400/40 bg-[#10201f] px-3 py-2 text-sm text-teal-100 shadow-lg">
                {notice}
              </div>
            )}
            {error && (
              <pre className="max-h-32 overflow-auto rounded-md border border-rose-400/40 bg-[#241517] px-3 py-2 text-sm whitespace-pre-wrap text-rose-100 shadow-lg">
                {error}
              </pre>
            )}
          </div>
        )}
        <Player
          track={selectedTrack}
          tracks={tracks}
          onSelectTrack={(track) => setSelectedTrackId(track.id)}
          onTrackUpdated={updateTrack}
          onOpenSettings={() => setSettingsOpen(true)}
        />
      </div>
      {settingsOpen && (
        <SettingsPanel
          onClose={() => {
            setSettingsOpen(false);
            checkApiKeys();
          }}
        />
      )}
    </main>
  );
}
