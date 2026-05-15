import os
import subprocess
import sys
from pathlib import Path


def separate(audio_path, output_dir):
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "demucs",
        "--two-stems",
        "vocals",
        "-o",
        str(output_root),
        str(audio_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("Python could not start Demucs.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        if "No module named demucs" in detail:
            raise RuntimeError("Demucs is not installed. Install backend requirements first.") from exc
        raise RuntimeError(detail or "Demucs failed while creating karaoke stems.") from exc

    track_name = os.path.splitext(os.path.basename(audio_path))[0]
    stem_dir = output_root / "htdemucs" / track_name
    vocals = stem_dir / "vocals.wav"
    instrumental = stem_dir / "no_vocals.wav"

    if not vocals.exists() or not instrumental.exists():
        raise RuntimeError("Demucs finished, but the expected stem files were not found.")

    return {
        "vocals": str(vocals),
        "no_vocals": str(instrumental),
    }
