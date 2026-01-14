import sys
import os

# Auto-launch with Streamlit if run directly with python
if __name__ == "__main__":
    try:
        from streamlit.web import cli as stcli
    except ImportError:
        try:
            import streamlit.cli as stcli
        except ImportError:
            print("Could not import streamlit. Please install it with: pip install streamlit")
            sys.exit(1)

    sys.argv = ["streamlit", "run", sys.argv[0]]
    sys.exit(stcli.main())

import streamlit as st
from pathlib import Path
import json

from config import Config
from services import LLMService, TTSService, STTService, ImageGenService
from utils import (
    clean_script_initial,
    segment_script_with_markers,
    parse_srt,
    calculate_image_durations
)
from media import get_audio_duration, create_video_from_images

# Page Config
st.set_page_config(page_title="AI Bible Story Generator", layout="wide")

# Session State Initialization
if "step" not in st.session_state:
    st.session_state.step = 1
if "project_slug" not in st.session_state:
    st.session_state.project_slug = ""
if "script_raw" not in st.session_state:
    st.session_state.script_raw = ""
if "prompts" not in st.session_state:
    st.session_state.prompts = []
if "images_data" not in st.session_state:
    st.session_state.images_data = []

def init_services():
    return {
        "llm": LLMService(),
        "tts": TTSService(),
        "stt": STTService(),
        "img": ImageGenService()
    }

# Load Services
try:
    services = init_services()
    st.sidebar.success("Services Initialized")

    if Config.N8N_SCRIPT_WEBHOOK_URL:
        st.sidebar.info("Using n8n Webhook for Script")
    else:
        st.sidebar.warning("Using Local API Keys for Script")

except Exception as e:
    st.sidebar.error(f"Error initializing services: {e}")
    st.stop()

# Helper to advance steps
def next_step():
    st.session_state.step += 1

def prev_step():
    st.session_state.step -= 1

# ==============================================================================
# STEP 1: SETUP & CONFIGURATION
# ==============================================================================
if st.session_state.step == 1:
    st.title("Step 1: Setup Story")

    # Check Config
    is_valid, msg = Config.validate()
    if not is_valid:
        st.error(msg)
        st.stop()

    col1, col2 = st.columns(2)
    with col1:
        topic = st.text_input("Biblical Story Topic", "José no Egito")
        num_images = st.number_input("Number of Images", min_value=3, max_value=50, value=10)

    if st.button("Generate Script"):
        with st.spinner("Generating script with LLM..."):
            try:
                # Generate Script
                script = services["llm"].generate_script(topic, num_images)
                st.session_state.script_raw = script

                # Generate Slug
                slug = topic.lower().replace(" ", "-") # Simplified slug generation
                st.session_state.project_slug = slug

                # Create directory
                Config.get_project_dir(slug)

                next_step()
                st.rerun()
            except Exception as e:
                st.error(f"Error generating script: {e}")

# ==============================================================================
# STEP 2: EDIT SCRIPT
# ==============================================================================
elif st.session_state.step == 2:
    st.title("Step 2: Review & Edit Script")

    st.info("Edit the script below. ensure you keep the [TROCAR_IMAGEM] markers!")

    new_script = st.text_area("Script", st.session_state.script_raw, height=600)
    st.session_state.script_raw = new_script

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Back"):
            prev_step()
            st.rerun()
    with col2:
        if st.button("Confirm Script & Generate Audio/Prompts"):
            next_step()
            st.rerun()

# ==============================================================================
# STEP 3: AUDIO & PROMPTS
# ==============================================================================
elif st.session_state.step == 3:
    st.title("Step 3: Generate Assets (Audio & Prompts)")

    project_dir = Config.get_project_dir(st.session_state.project_slug)

    # State for this step to avoid re-running heavy tasks
    if "assets_generated" not in st.session_state:
        st.session_state.assets_generated = False

    if not st.session_state.assets_generated:
        with st.status("Generating Assets...", expanded=True) as status:
            try:
                # 1. Process Script
                st.write("Processing Script...")
                script_clean, script_markers = clean_script_initial(st.session_state.script_raw)

                # Save processed script
                with open(project_dir / "roteiro_com_marcadores.txt", "w") as f:
                    f.write(script_markers)

                # 2. TTS
                st.write("Generating Audio (TTS)...")
                audio_path = project_dir / "narracao.mp3"
                if not audio_path.exists():
                     services["tts"].generate_audio(script_clean, audio_path)

                # 3. STT (Transcribe for SRT)
                st.write("Transcribing Audio (SRT)...")
                srt_content = services["stt"].transcribe(audio_path)
                with open(project_dir / "narracao.srt", "w") as f:
                    f.write(srt_content)

                # 4. Generate Prompts
                st.write("Generating Image Prompts...")
                segments = segment_script_with_markers(script_markers)

                # Simple join for context
                segmented_text = "\n\n".join([f"{i+1}. {s}" for i, s in enumerate(segments)])

                prompts_list = services["llm"].generate_prompts(segmented_text)
                st.session_state.prompts = prompts_list

                st.session_state.assets_generated = True
                status.update(label="Assets Generated Successfully!", state="complete", expanded=False)

            except Exception as e:
                st.error(f"Error during asset generation: {e}")
                st.stop()

    # Display & Edit Prompts
    st.subheader("Edit Image Prompts")

    updated_prompts = []
    for i, p in enumerate(st.session_state.prompts):
        with st.expander(f"Scene {i+1}: {p.get('image', 'img')}"):
            new_prompt = st.text_area(f"Prompt {i+1}", p['prompt'], key=f"p_{i}")
            updated_prompts.append({"image": p['image'], "prompt": new_prompt})

    st.session_state.prompts = updated_prompts

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Back"):
            st.session_state.assets_generated = False # Reset if going back? maybe not
            prev_step()
            st.rerun()
    with col2:
        if st.button("Generate Images & Video"):
            next_step()
            st.rerun()

# ==============================================================================
# STEP 4: IMAGES & VIDEO PRODUCTION
# ==============================================================================
elif st.session_state.step == 4:
    st.title("Step 4: Production")

    project_dir = Config.get_project_dir(st.session_state.project_slug)

    if "production_done" not in st.session_state:
        st.session_state.production_done = False

    if not st.session_state.production_done:
        start_btn = st.button("Start Production")
        if start_btn:
            progress_bar = st.progress(0)
            status_text = st.empty()

            try:
                # 1. Generate Images
                total_images = len(st.session_state.prompts)

                for i, p_data in enumerate(st.session_state.prompts):
                    status_text.text(f"Generating Image {i+1}/{total_images}...")
                    image_name = p_data['image'] # e.g. "image_1"
                    image_path = project_dir / f"{image_name}.jpg"

                    if not image_path.exists():
                         services["img"].generate_image_openai(p_data['prompt'], image_path)

                    progress_bar.progress((i + 1) / (total_images + 2))

                # 2. Sync Logic (Calculate Durations)
                status_text.text("Synchronizing Script with Audio...")

                # Read SRT
                with open(project_dir / "narracao.srt", "r") as f:
                    srt_content = f.read()
                subtitles = parse_srt(srt_content)

                # Get script segments again
                with open(project_dir / "roteiro_com_marcadores.txt", "r") as f:
                    script_markers = f.read()
                segments = segment_script_with_markers(script_markers)

                # Get audio duration
                audio_path = project_dir / "narracao.mp3"
                audio_duration = get_audio_duration(audio_path)

                # Calculate
                images_data = calculate_image_durations(segments, subtitles, audio_duration)
                st.session_state.images_data = images_data

                progress_bar.progress((total_images + 1) / (total_images + 2))

                # 3. Render Video
                status_text.text("Rendering Final Video (FFmpeg)...")
                final_video_path = create_video_from_images(images_data, audio_path, project_dir)

                progress_bar.progress(1.0)
                status_text.text("Production Complete!")
                st.session_state.production_done = True
                st.balloons()
                st.rerun()

            except Exception as e:
                st.error(f"Production failed: {e}")

    else:
        st.success("Video Generated Successfully!")
        project_dir = Config.get_project_dir(st.session_state.project_slug)
        video_path = project_dir / "video_final.mp4"

        if video_path.exists():
            st.video(str(video_path))

        if st.button("Start New Project"):
            st.session_state.step = 1
            st.session_state.assets_generated = False
            st.session_state.production_done = False
            st.rerun()
