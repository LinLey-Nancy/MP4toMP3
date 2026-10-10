from transcribe.align import (
    assign_speakers, merge_adjacent, format_transcript, format_ts,
)


def test_format_ts():
    assert format_ts(0) == "00:00:00"
    assert format_ts(65.9) == "00:01:05"
    assert format_ts(3661.2) == "01:01:01"


def test_assign_speakers_picks_max_overlap():
    asr = [{"start": 0.0, "end": 10.0, "text": "你好"}]
    diar = [
        {"start": 0.0, "end": 3.0, "speaker": 0},
        {"start": 3.0, "end": 10.0, "speaker": 1},
    ]
    result = assign_speakers(asr, diar)
    assert result[0]["speaker"] == 1  # 7 秒重叠 > 3 秒


def test_assign_speakers_no_diarization_defaults_to_zero():
    asr = [{"start": 0.0, "end": 5.0, "text": "喂"}]
    assert assign_speakers(asr, [])[0]["speaker"] == 0


def test_assign_speakers_gap_defaults_to_zero():
    asr = [{"start": 0.0, "end": 2.0, "text": "嗯"}]
    diar = [{"start": 5.0, "end": 9.0, "speaker": 3}]
    assert assign_speakers(asr, diar)[0]["speaker"] == 0


def test_merge_adjacent_same_speaker():
    segs = [
        {"start": 0.0, "end": 2.0, "text": "先过一下", "speaker": 1},
        {"start": 2.0, "end": 5.0, "text": "上周进度", "speaker": 1},
        {"start": 5.0, "end": 8.0, "text": "好的", "speaker": 2},
    ]
    merged = merge_adjacent(segs)
    assert len(merged) == 2
    assert merged[0]["end"] == 5.0
    assert merged[0]["text"] == "先过一下 上周进度"


def test_format_transcript():
    segs = [
        {"start": 2.0, "end": 5.0, "text": "我们先过一下进度。", "speaker": 0},
        {"start": 15.0, "end": 20.0, "text": "联调基本完成了。", "speaker": 1},
    ]
    text = format_transcript(segs)
    assert text == (
        "[00:00:02] 说话人1: 我们先过一下进度。\n"
        "[00:00:15] 说话人2: 联调基本完成了。\n"
    )
