from src.utils import calculate_durations_from_words, parse_json_transcription, segment_script_with_markers
import json
import traceback

def test_json_parsing():
    print("Testing JSON Parsing...")

    # Case 1: Whisper verbose_json style
    json_whisper = json.dumps({
        "segments": [
            {
                "words": [
                    {"word": "Hello", "start": 0.0, "end": 0.5},
                    {"word": "world", "start": 0.5, "end": 1.0}
                ]
            },
            {
                "words": [
                    {"word": "Next", "start": 1.0, "end": 1.5},
                    {"word": "segment", "start": 1.5, "end": 2.0}
                ]
            }
        ]
    })
    words = parse_json_transcription(json_whisper)
    assert len(words) == 4
    assert words[0]['word'] == "Hello"
    assert words[2]['word'] == "Next"

    # Case 2: List of objects
    json_list = json.dumps([
        {"word": "Direct", "start": 0.0, "end": 0.5},
        {"word": "List", "start": 0.5, "end": 1.0}
    ])
    words2 = parse_json_transcription(json_list)
    assert len(words2) == 2
    assert words2[0]['word'] == "Direct"

    print("JSON Parsing OK")

def test_sync_logic_json():
    print("Testing JSON Sync Logic...")

    # Mock Script
    script = "Scene one starts [TROCAR_IMAGEM] Scene two begins [TROCAR_IMAGEM] Finale now."
    segments = segment_script_with_markers(script)
    # Segments: ["Scene one starts", "Scene two begins", "Finale now."]

    # Mock Word Data
    # 0.0-1.0: Scene one starts
    # 1.0-2.0: ...
    # 2.0-3.0: Scene two begins (Anchor "Scene two begins" at 2.0)
    # 5.0-6.0: Finale now (Anchor "Finale now" at 5.0)

    word_data = [
        {"word": "Scene", "start": 0.0, "end": 0.3},
        {"word": "one", "start": 0.3, "end": 0.6},
        {"word": "starts", "start": 0.6, "end": 1.0},

        {"word": "some", "start": 1.0, "end": 1.5},
        {"word": "filler", "start": 1.5, "end": 2.0},

        {"word": "Scene", "start": 2.0, "end": 2.3}, # Target for Segment 2
        {"word": "two", "start": 2.3, "end": 2.6},
        {"word": "begins", "start": 2.6, "end": 3.0},

        {"word": "more", "start": 3.0, "end": 4.0},
        {"word": "talk", "start": 4.0, "end": 5.0},

        {"word": "Finale", "start": 5.0, "end": 5.5}, # Target for Segment 3
        {"word": "now", "start": 5.5, "end": 6.0}
    ]

    total_duration = 10.0

    # Logic:
    # Segment 1 ends where Segment 2 starts.
    # Segment 2 starts at "Scene two begins" -> 2.0
    # So Segment 1 Duration = 2.0 - 0.0 = 2.0

    # Segment 2 ends where Segment 3 starts.
    # Segment 3 starts at "Finale now" -> 5.0
    # So Segment 2 Duration = 5.0 - 2.0 = 3.0

    # Segment 3 ends at total duration (10.0)
    # So Segment 3 Duration = 10.0 - 5.0 = 5.0

    durations = calculate_durations_from_words(segments, word_data, total_duration)
    print(f"Durations: {durations}")

    assert durations[0]['duration'] == 2.0
    assert durations[1]['duration'] == 3.0
    assert durations[2]['duration'] == 5.0

    print("JSON Sync Logic OK")

if __name__ == "__main__":
    try:
        test_json_parsing()
        test_sync_logic_json()
        print("ALL TESTS PASSED")
    except Exception:
        traceback.print_exc()
        exit(1)
