def format_ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _overlap(a_start, a_end, b_start, b_end):
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def assign_speakers(asr_segments, diar_segments):
    for seg in asr_segments:
        best_speaker, best_overlap = 0, 0.0
        for d in diar_segments:
            ov = _overlap(seg["start"], seg["end"], d["start"], d["end"])
            if ov > best_overlap:
                best_speaker, best_overlap = d["speaker"], ov
        seg["speaker"] = best_speaker
    return asr_segments


def merge_adjacent(segments):
    merged = []
    for seg in segments:
        if merged and merged[-1]["speaker"] == seg["speaker"]:
            merged[-1]["end"] = seg["end"]
            merged[-1]["text"] += " " + seg["text"]
        else:
            merged.append(dict(seg))
    return merged


def format_transcript(segments):
    return "".join(
        f"[{format_ts(s['start'])}] 说话人{s['speaker'] + 1}: {s['text'].strip()}\n"
        for s in segments
    )
