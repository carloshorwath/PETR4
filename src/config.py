import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists
load_dotenv()

class Config:
    # API Keys
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

    # External Services URLs
    SPEACHES_URL = os.getenv("SPEACHES_URL", "http://localhost:8000/v1/audio/transcriptions")

    # Models
    LLM_MODEL = os.getenv("LLM_MODEL", "x-ai/grok-4-fast:free") # Default from n8n
    TTS_MODEL = os.getenv("TTS_MODEL", "tts-1-hd")
    TTS_VOICE = os.getenv("TTS_VOICE", "onyx")
    IMAGE_MODEL_OPENAI = "dall-e-2"
    IMAGE_MODEL_GOOGLE = "models/gemini-2.0-flash-preview-image-generation"

    # Paths
    BASE_DIR = Path(os.getenv("BASE_OUTPUT_DIR", "./output"))
    FFMPEG_BINARY = os.getenv("FFMPEG_BINARY", "ffmpeg")
    FFPROBE_BINARY = os.getenv("FFPROBE_BINARY", "ffprobe")

    @staticmethod
    def get_project_dir(slug: str) -> Path:
        path = Config.BASE_DIR / slug
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def validate():
        missing = []
        if not Config.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        if not Config.OPENROUTER_API_KEY:
            missing.append("OPENROUTER_API_KEY")
        # Google Key is optional if user chooses OpenAI for images, but let's list it
        if not Config.GOOGLE_API_KEY:
            pass # make it optional for now or warn

        if missing:
            return False, f"Missing environment variables: {', '.join(missing)}"
        return True, "Configuration OK"
