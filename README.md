# AI Bible Story Generator

This project is a Python application that replicates the n8n workflow for generating Bible stories with AI narration and images.

## Features
- **Story Generation**: Uses LLMs (OpenRouter) to write script.
- **Audio**: Uses OpenAI TTS.
- **Transcriptions**: Uses Speaches (or OpenAI Whisper) for SRT generation.
- **Image Generation**: Uses OpenAI DALL-E (or Google Gemini).
- **Video Assembly**: Uses FFmpeg to combine images and audio with synchronized timing.

## Architecture

This app is designed to work in two modes:
1.  **n8n Webhook Mode (Recommended)**: All AI logic (Script, TTS, Images) is offloaded to n8n workflows. The app acts as a frontend and video assembler.
2.  **Standalone Mode**: The app calls APIs (OpenAI, OpenRouter) directly using local keys.

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
    *Note: The `openai` python package is NOT required. This app uses standard HTTP requests.*

2.  **Install FFmpeg**:
    Ensure `ffmpeg` and `ffprobe` are installed and in your system PATH.

3.  **Environment Variables**:
    Create a `.env` file in the root directory.

    **Configuration for n8n Webhooks:**
    ```ini
    N8N_SCRIPT_WEBHOOK_URL=http://localhost:5678/webhook/script
    N8N_TTS_WEBHOOK_URL=http://localhost:5678/webhook/tts
    N8N_PROMPTS_WEBHOOK_URL=http://localhost:5678/webhook/prompts
    N8N_IMAGE_WEBHOOK_URL=http://localhost:5678/webhook/image
    ```

    **Configuration for Standalone Mode (Fallbacks):**
    ```ini
    OPENAI_API_KEY=sk-... (For TTS, Images, Whisper)
    OPENROUTER_API_KEY=sk-... (For Script, Prompts)
    SPEACHES_URL=http://localhost:8000/v1/audio/transcriptions (Optional local STT)
    ```

## Webhook Contracts
If creating n8n workflows, ensure they match these inputs/outputs:

*   **Script Webhook**:
    *   **Input (JSON)**: `{"topic": "Story Topic", "imageCount": 10}`
    *   **Output (JSON)**: `{"script": "Full script text..."}`

*   **TTS Webhook**:
    *   **Input (JSON)**: `{"text": "Text to speak"}`
    *   **Output (Binary)**: MP3 audio file.

*   **Prompts Webhook**:
    *   **Input (JSON)**: `{"script_segmented": "1. Scene one...\n2. Scene two..."}`
    *   **Output (JSON)**: `{"image_prompts": [{"image": "image_1", "prompt": "..."}, ...]}`

*   **Image Webhook**:
    *   **Input (JSON)**: `{"prompt": "A beautiful painting of..."}`
    *   **Output (Binary)**: JPG/PNG image file.

## Running the App

Run the Streamlit interface:
```bash
# Windows
run_app.bat

# Linux/Mac
./run_app.sh
```
Or manually:
```bash
streamlit run src/app.py
```
