def clamp_score(value):
    return round(max(0, min(1, float(value))) * 100)


def _grade(total):
    if total >= 92:
        return "S"
    if total >= 84:
        return "A"
    if total >= 74:
        return "B"
    if total >= 62:
        return "C"
    return "D"


def _tips(scores, timing_offset):
    tips = []
    if abs(timing_offset) > 0.28:
        direction = "early" if timing_offset < 0 else "late"
        tips.append(f"Your take is landing about {abs(timing_offset):.2f}s {direction}.")
    if scores["pitch"] < 65:
        tips.append("Pitch was the main limiter. Try a lower volume backing track and lock onto the vocal melody.")
    if scores["timing"] < 65:
        tips.append("Timing was loose. Start with shorter phrases and match the first word of each line.")
    if scores["completion"] < 70:
        tips.append("The recording missed a lot of the vocal sections.")
    if not tips:
        tips.append("Strong take. Small timing and pitch differences are normal for live vocals.")
    return tips[:3]


def _voice_envelope(signal, frame_length=2048, hop_length=512):
    import librosa
    import numpy as np

    rms = librosa.feature.rms(y=signal, frame_length=frame_length, hop_length=hop_length)[0]
    if not len(rms):
        return rms
    rms = rms / (np.max(rms) + 1e-9)
    return rms


def _estimate_timing_offset(original, user, sr):
    import numpy as np

    orig_env = _voice_envelope(original)
    user_env = _voice_envelope(user)
    length = min(len(orig_env), len(user_env))
    if length < 4:
        return 0.0, 0

    orig_env = orig_env[:length] - np.mean(orig_env[:length])
    user_env = user_env[:length] - np.mean(user_env[:length])
    if np.allclose(orig_env, 0) or np.allclose(user_env, 0):
        return 0.0, 0

    corr = np.correlate(user_env, orig_env, mode="full")
    max_shift_frames = int(round(1.8 * sr / 512))
    center = len(orig_env) - 1
    lo = max(0, center - max_shift_frames)
    hi = min(len(corr), center + max_shift_frames + 1)
    local = corr[lo:hi]
    best = int(np.argmax(local)) + lo
    lag_frames = best - center
    return round(lag_frames * 512 / sr, 3), lag_frames


def _shift_frames(values, lag_frames, fill_value=0):
    import numpy as np

    shifted = np.full_like(values, fill_value)
    if abs(lag_frames) >= len(values):
        return shifted
    if lag_frames > 0:
        shifted[:-lag_frames] = values[lag_frames:]
    elif lag_frames < 0:
        shifted[-lag_frames:] = values[:lag_frames]
    else:
        shifted = values
    return shifted


def score(original_vocals_path, user_recording_path):
    try:
        import librosa
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Karaoke scoring needs librosa. Install backend requirements first.") from exc

    orig, sr = librosa.load(original_vocals_path, sr=22050, mono=True)
    user, _ = librosa.load(user_recording_path, sr=22050, mono=True)

    if len(orig) == 0 or len(user) == 0:
        return {
            "pitch": 0,
            "timing": 0,
            "consistency": 0,
            "completion": 0,
            "total": 0,
            "grade": "D",
            "timing_offset": 0,
            "tips": ["No usable vocal audio was detected."],
        }

    timing_offset, lag_frames = _estimate_timing_offset(orig, user, sr)

    orig_f0, _, orig_voiced = librosa.pyin(orig, fmin=65, fmax=2093, sr=sr)
    user_f0, _, user_voiced = librosa.pyin(user, fmin=65, fmax=2093, sr=sr)

    user_f0 = _shift_frames(user_f0, lag_frames, fill_value=np.nan)
    user_voiced = _shift_frames(user_voiced, lag_frames, fill_value=False)

    length = min(len(orig_f0), len(user_f0), len(orig_voiced), len(user_voiced))
    orig_f0 = orig_f0[:length]
    user_f0 = user_f0[:length]
    orig_voiced = orig_voiced[:length]
    user_voiced = user_voiced[:length]

    both_voiced = orig_voiced & user_voiced
    if both_voiced.sum() == 0:
        pitch_score = 0
    else:
        cents = np.abs(1200 * np.log2(user_f0[both_voiced] / orig_f0[both_voiced]))
        cents = np.mod(cents + 600, 1200) - 600
        pitch_score = max(0, 1 - float(np.nanmedian(np.abs(cents)) / 180))

    orig_voice_count = max(float(orig_voiced.sum()), 1)
    user_voice_count = float(user_voiced.sum())
    completion = min(1, user_voice_count / orig_voice_count)

    if user_voiced.sum() > 1:
        stable_f0 = user_f0[user_voiced]
        stable_f0 = stable_f0[~np.isnan(stable_f0)]
        consistency = 1 - float(np.std(stable_f0) / 180) if len(stable_f0) else 0
    else:
        consistency = 0

    orig_activity = _voice_envelope(orig)[:length]
    user_activity = _voice_envelope(user)[:length]
    user_activity = _shift_frames(user_activity, lag_frames, fill_value=0)
    active_similarity = 0
    if len(orig_activity) and len(user_activity):
        active_similarity = 1 - float(np.mean(np.abs(orig_activity - user_activity)))
    timing = min(1, max(0, (float(both_voiced.sum()) / orig_voice_count) * 0.65 + active_similarity * 0.35))
    total = pitch_score * 0.4 + timing * 0.3 + max(0, consistency) * 0.2 + completion * 0.1

    scores = {
        "pitch": clamp_score(pitch_score),
        "timing": clamp_score(timing),
        "consistency": clamp_score(consistency),
        "completion": clamp_score(completion),
        "total": clamp_score(total),
    }

    return {
        **scores,
        "grade": _grade(scores["total"]),
        "timing_offset": timing_offset,
        "tips": _tips(scores, timing_offset),
    }
