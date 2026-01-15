from src.utils import calculate_image_durations, segment_script_with_markers, parse_srt
import traceback

def test_sync_logic():
    print("Testing Sync Logic...")

    # Mock Script with markers (Distinct beginnings)
    script = "Scene one starts here [TROCAR_IMAGEM] Scene two follows now [TROCAR_IMAGEM] Finale is here."
    segments = segment_script_with_markers(script)

    # Mock SRT
    srt_content = """1
00:00:00,000 --> 00:00:02,000
Scene one starts here

2
00:00:02,000 --> 00:00:05,000
and we continue.

3
00:00:05,000 --> 00:00:07,000
Scene two follows now

4
00:00:07,000 --> 00:00:10,000
and more text.

5
00:00:10,000 --> 00:00:12,000
Finale is here.
"""
    subtitles = parse_srt(srt_content)
    total_duration = 12.0

    durations = calculate_image_durations(segments, subtitles, total_duration)
    print(f"Durations: {durations}")

    # Image 1: 0.0 to 2.0 = 2.0
    assert durations[0]['duration'] == 2.0

    # Image 2: 2.0 to 7.0 = 5.0
    assert durations[1]['duration'] == 5.0

    # Image 3: 7.0 to 12.0 = 5.0
    assert durations[2]['duration'] == 5.0

    print("Duration Calculation OK (Faithful to JS Logic)")

def test_sync_fallback():
    print("Testing Sync Fallback...")

    # Script where 3rd word doesn't match in SRT (e.g. slight difference)
    # Segment 2: "Scene two changed now" (SRT has "Scene two follows now")
    # But "Scene two" (2 words) should match.
    script = "Scene one starts here [TROCAR_IMAGEM] Scene two changed now [TROCAR_IMAGEM] Finale is here."
    segments = segment_script_with_markers(script)

    srt_content = """1
00:00:00,000 --> 00:00:02,000
Scene one starts here

2
00:00:02,000 --> 00:00:05,000
and we continue.

3
00:00:05,000 --> 00:00:07,000
Scene two follows now

4
00:00:07,000 --> 00:00:10,000
and more text.

5
00:00:10,000 --> 00:00:12,000
Finale is here.
"""
    subtitles = parse_srt(srt_content)
    total_duration = 12.0

    durations = calculate_image_durations(segments, subtitles, total_duration)
    print(f"Fallback Durations: {durations}")

    # Should still find the transition at 2.0s using 2-word match
    assert durations[0]['duration'] == 2.0

    print("Fallback Logic OK")

if __name__ == "__main__":
    try:
        test_sync_logic()
        test_sync_fallback()
        print("ALL TESTS PASSED")
    except Exception:
        traceback.print_exc()
        exit(1)
