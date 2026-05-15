def clamp_score(value):
    return round(max(0, min(1, float(value))) * 100)


def score(original_vocals_path, user_recording_path):
    try:
        import librosa
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Karaoke scoring needs librosa. Install backend requirements first.") from exc

    orig, sr = librosa.load(original_vocals_path, sr=22050, mono=True)
    user, _ = librosa.load(user_recording_path, sr=22050, mono=True)

    if len(orig) == 0 or len(user) == 0:
        return {"pitch": 0, "timing": 0, "consistency": 0, "completion": 0, "total": 0}

    orig_f0, _, orig_voiced = librosa.pyin(orig, fmin=65, fmax=2093, sr=sr)
    user_f0, _, user_voiced = librosa.pyin(user, fmin=65, fmax=2093, sr=sr)

    length = min(len(orig_f0), len(user_f0), len(orig_voiced), len(user_voiced))
    orig_f0 = orig_f0[:length]
    user_f0 = user_f0[:length]
    orig_voiced = orig_voiced[:length]
    user_voiced = user_voiced[:length]

    both_voiced = orig_voiced & user_voiced
    if both_voiced.sum() == 0:
        pitch_score = 0
    else:
        diff = np.abs(orig_f0[both_voiced] - user_f0[both_voiced])
        pitch_score = max(0, 1 - float(np.nanmean(diff) / 70))

    orig_voice_count = max(float(orig_voiced.sum()), 1)
    user_voice_count = float(user_voiced.sum())
    completion = min(1, user_voice_count / orig_voice_count)

    if user_voiced.sum() > 1:
        stable_f0 = user_f0[user_voiced]
        stable_f0 = stable_f0[~np.isnan(stable_f0)]
        consistency = 1 - float(np.std(stable_f0) / 180) if len(stable_f0) else 0
    else:
        consistency = 0

    timing = min(1, float(both_voiced.sum()) / orig_voice_count)
    total = pitch_score * 0.4 + timing * 0.3 + max(0, consistency) * 0.2 + completion * 0.1

    return {
        "pitch": clamp_score(pitch_score),
        "timing": clamp_score(timing),
        "consistency": clamp_score(consistency),
        "completion": clamp_score(completion),
        "total": clamp_score(total),
    }
