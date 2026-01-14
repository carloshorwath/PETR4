# AI Bible Story Generator

This project is a Python application that replicates the n8n workflow for generating Bible stories with AI narration and images.

## Features
- **Story Generation**: Uses LLMs (OpenRouter) to write script.
- **Audio**: Uses OpenAI TTS.
- **Transcriptions**: Uses Speaches (or OpenAI Whisper) for SRT generation.
- **Image Generation**: Uses OpenAI DALL-E (or Google Gemini).
- **Video Assembly**: Uses FFmpeg to combine images and audio with synchronized timing.

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Install FFmpeg**:
    Ensure `ffmpeg` and `ffprobe` are installed and in your system PATH.

3.  **Environment Variables**:
    Create a `.env` file in the root directory with the following keys:
    ```ini
    OPENAI_API_KEY=sk-...
    OPENROUTER_API_KEY=sk-...
    # Optional
    GOOGLE_API_KEY=...
    SPEACHES_URL=http://localhost:8000/v1/audio/transcriptions
    ```

## Running the App

Run the Streamlit interface:
```bash
streamlit run src/app.py
```

## Workflow
1.  **Setup**: Enter topic (e.g., "Daniel na Cova dos Leões") and number of images.
2.  **Edit Script**: Review the generated script. Keep the `[TROCAR_IMAGEM]` markers.
3.  **Generate Assets**: The app generates audio, SRT subtitles, and image prompts. You can edit the prompts.
4.  **Production**: The app generates images and renders the final MP4 video.
