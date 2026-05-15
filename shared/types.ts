export type TrackStatus = "unprocessed" | "fetching_lyrics" | "aligning" | "ready" | "needs_review" | "karaoke_ready";

export interface Track {
  id: string;
  title: string | null;
  artist: string | null;
  album: string | null;
  path: string;
  duration: number | null;
  cover_art: string | null;
  language: string | null;
  status: TrackStatus;
  ttml_path: string | null;
  vocals_path: string | null;
  instrumental_path: string | null;
  created_at: string;
}
