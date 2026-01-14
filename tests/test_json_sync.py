import sys
import os
import json
sys.path.append(os.getcwd()) # Ensure root is in path

from src.utils import parse_json_transcription, calculate_durations_from_words, clean_text_for_search

def test_json_sync():
    print("Testing JSON Sync Logic...")

    # Mock Segments
    # Segment 1 starts at 0.0
    # Segment 2 starts at "Scene two starts"
    # Segment 3 starts at "Finale is here"
    segments = [
        "Scene one starts here",
        "Scene two starts now",
        "Finale is here"
    ]

    # Mock Word Data (from Whisper)
    # 0.0 - 2.0: Scene one starts here
    # 2.0 - 4.0: filler
    # 4.0 - 5.0: Scene two starts now
    # 8.0 - 9.0: Finale is here
    word_data = [
        {"word": "Scene", "start": 0.0, "end": 0.5},
        {"word": "one", "start": 0.5, "end": 1.0},
        {"word": "starts", "start": 1.0, "end": 1.5},
        {"word": "here", "start": 1.5, "end": 2.0},
        {"word": "filler", "start": 2.0, "end": 4.0},
        {"word": "Scene", "start": 4.0, "end": 4.5},
        {"word": "two", "start": 4.5, "end": 5.0},
        {"word": "starts", "start": 5.0, "end": 5.5},
        {"word": "now", "start": 5.5, "end": 6.0},
        {"word": "more", "start": 6.0, "end": 8.0},
        {"word": "Finale", "start": 8.0, "end": 8.5},
        {"word": "is", "start": 8.5, "end": 9.0},
        {"word": "here", "start": 9.0, "end": 9.5}
    ]

    total_duration = 10.0

    # Expected behavior:
    # Segment 1: Always starts at 0.0.
    # Segment 2: Search for "Scene two starts". found at index 5, start 4.0.
    # Segment 3: Search for "Finale is here". found at index 10, start 8.0.

    # Durations:
    # Image 1 (Segment 1): 4.0 - 0.0 = 4.0
    # Image 2 (Segment 2): 8.0 - 4.0 = 4.0
    # Image 3 (Segment 3): 10.0 - 8.0 = 2.0

    durations = calculate_durations_from_words(segments, word_data, total_duration)

    print(f"Durations: {durations}")

    assert len(durations) == 3
    assert durations[0]['image'] == 'image_1'
    assert durations[0]['duration'] == 4.0
    assert durations[1]['image'] == 'image_2'
    assert durations[1]['duration'] == 4.0
    assert durations[2]['image'] == 'image_3'
    assert durations[2]['duration'] == 2.0

    print("JSON Sync Logic OK")

def test_parse_json():
    print("Testing Parse JSON...")
    json_str = '{"words": [{"word": "Test", "start": 0.0}]}'
    words = parse_json_transcription(json_str)
    assert len(words) == 1
    assert words[0]['word'] == "Test"

    # Test list format
    json_list_str = '[{"word": "Test", "start": 0.0}]'
    words = parse_json_transcription(json_list_str)
    assert len(words) == 1

    print("Parse JSON OK")

if __name__ == "__main__":
    try:
        test_parse_json()
        test_json_sync()
        print("ALL TESTS PASSED")
    except Exception as e:
        print(f"FAILED: {e}")
        exit(1)
