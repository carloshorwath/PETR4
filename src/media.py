import subprocess
import json
import re
from pathlib import Path
from config import Config

def get_audio_duration(audio_path: Path) -> float:
    """
    Returns the duration of the audio file in seconds using ffprobe.
    """
    cmd = [
        Config.FFPROBE_BINARY,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"Error getting audio duration: {e}")
        return 0.0

def create_video_from_images(images_data: list, audio_path: Path, output_dir: Path, video_format: str = "Vertical (9:16) - Full HD (1080x1920)") -> Path:
    """
    Generates the final video using FFmpeg.
    images_data: List of dicts [{'image': 'image_1', 'duration': 5.0}, ...]
    video_format: String like "Vertical (9:16) - Full HD (1080x1920)"
    """
    # Parse resolution from string
    # e.g. "Vertical (9:16) - Full HD (1080x1920)" -> 1080, 1920
    match = re.search(r"\((\d+)x(\d+)\)", video_format)
    if match:
        target_width = int(match.group(1))
        target_height = int(match.group(2))
    else:
        # Default fallback
        target_width = 1080
        target_height = 1920
        print(f"Warning: Could not parse resolution from '{video_format}'. Using 1080x1920.")

    print(f"Rendering video at {target_width}x{target_height}")

    fade_duration = 0.5

    inputs = []
    filter_parts = []
    concat_parts = []

    valid_image_count = 0

    # 1. Prepare inputs and filters
    for i, img_info in enumerate(images_data):
        image_name = img_info['image']
        duration = float(img_info['duration'])

        if duration < 0.1:
            continue

        # Check for existing image extension
        found_image = None
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            possible_path = output_dir / f"{image_name}{ext}"
            if possible_path.exists():
                found_image = possible_path
                break

        if not found_image:
            raise FileNotFoundError(f"Image not found: {image_name} (checked .jpg, .jpeg, .png, .webp)")

        # Add input
        inputs.extend(["-loop", "1", "-t", str(duration), "-i", str(found_image)])

        # Calculate fade out start time
        st_out = max(0, duration - fade_duration)

        # Create filter chain for this input
        # [0:v]scale=...[v0];
        filter_str = (
            f"[{i}:v]"
            f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,"
            f"fade=t=in:st=0:d={fade_duration},"
            f"fade=t=out:st={st_out}:d={fade_duration},"
            f"setpts=PTS-STARTPTS"
            f"[v{i}]"
        )
        filter_parts.append(filter_str)
        concat_parts.append(f"[v{i}]")

        valid_image_count += 1

    if valid_image_count == 0:
        raise ValueError("No valid images to create video.")

    # 2. Construct Filter Complex
    concat_filter = f"{''.join(concat_parts)}concat=n={valid_image_count}:v=1:a=0[outv]"
    full_filter = f"{';'.join(filter_parts)};{concat_filter}"

    video_no_audio = output_dir / "video_sem_audio.mp4"
    final_video = output_dir / "video_final.mp4"

    # 3. Command 1: Create Video Stream
    cmd_video = [
        Config.FFMPEG_BINARY,
        *inputs,
        "-filter_complex", full_filter,
        "-map", "[outv]",
        "-c:v", "libx264",
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-y",
        str(video_no_audio)
    ]

    print("Running FFmpeg video generation...")
    subprocess.run(cmd_video, check=True)

    # 4. Command 2: Merge with Audio
    cmd_merge = [
        Config.FFMPEG_BINARY,
        "-i", str(video_no_audio),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-y",
        str(final_video)
    ]

    print("Running FFmpeg audio merge...")
    subprocess.run(cmd_merge, check=True)

    return final_video
