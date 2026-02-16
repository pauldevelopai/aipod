from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # API Keys
    auphonic_api_key: str = ""
    happyscribe_api_key: str = ""
    deepl_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    elevenlabs_api_key: str = ""
    hf_token: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # App
    secret_key: str = "change-me"
    upload_dir: str = "uploads"
    output_dir: str = "outputs"
    database_url: str = "sqlite:///data/aipod.db"

    model_config = {"env_file": str(BASE_DIR / ".env"), "env_file_encoding": "utf-8"}


settings = Settings()

# --- Supported Languages (single source of truth) ---
SUPPORTED_LANGUAGES = [
    {"code": "en", "name": "English", "deepl": "EN", "happyscribe": "en", "elevenlabs": "en"},
    {"code": "es", "name": "Spanish", "deepl": "ES", "happyscribe": "es", "elevenlabs": "es"},
    {"code": "fr", "name": "French", "deepl": "FR", "happyscribe": "fr", "elevenlabs": "fr"},
    {"code": "de", "name": "German", "deepl": "DE", "happyscribe": "de", "elevenlabs": "de"},
    {"code": "it", "name": "Italian", "deepl": "IT", "happyscribe": "it", "elevenlabs": "it"},
    {"code": "pt", "name": "Portuguese (BR)", "deepl": "PT-BR", "happyscribe": "pt-BR", "elevenlabs": "pt"},
    {"code": "nl", "name": "Dutch", "deepl": "NL", "happyscribe": "nl", "elevenlabs": "nl"},
    {"code": "pl", "name": "Polish", "deepl": "PL", "happyscribe": "pl", "elevenlabs": "pl"},
    {"code": "ja", "name": "Japanese", "deepl": "JA", "happyscribe": "ja", "elevenlabs": "ja"},
    {"code": "ko", "name": "Korean", "deepl": "KO", "happyscribe": "ko", "elevenlabs": "ko"},
    {"code": "zh", "name": "Chinese (Mandarin)", "deepl": "ZH", "happyscribe": "zh", "elevenlabs": "zh"},
    {"code": "hi", "name": "Hindi", "deepl": "HI", "happyscribe": "hi", "elevenlabs": "hi"},
    {"code": "ar", "name": "Arabic", "deepl": "AR", "happyscribe": "ar", "elevenlabs": "ar"},
    {"code": "tr", "name": "Turkish", "deepl": "TR", "happyscribe": "tr", "elevenlabs": "tr"},
    {"code": "id", "name": "Indonesian", "deepl": "ID", "happyscribe": "id", "elevenlabs": "id"},
    {"code": "sv", "name": "Swedish", "deepl": "SV", "happyscribe": "sv", "elevenlabs": "sv"},
    {"code": "cs", "name": "Czech", "deepl": "CS", "happyscribe": "cs", "elevenlabs": "cs"},
    {"code": "ro", "name": "Romanian", "deepl": "RO", "happyscribe": "ro", "elevenlabs": "ro"},
    {"code": "bg", "name": "Bulgarian", "deepl": "BG", "happyscribe": "bg", "elevenlabs": "bg"},
    {"code": "fi", "name": "Finnish", "deepl": "FI", "happyscribe": "fi", "elevenlabs": "fi"},
    {"code": "da", "name": "Danish", "deepl": "DA", "happyscribe": "da", "elevenlabs": "da"},
    {"code": "el", "name": "Greek", "deepl": "EL", "happyscribe": "el", "elevenlabs": "el"},
    {"code": "sk", "name": "Slovak", "deepl": "SK", "happyscribe": "sk", "elevenlabs": "sk"},
    {"code": "hr", "name": "Croatian", "deepl": "HR", "happyscribe": "hr", "elevenlabs": "hr"},
    {"code": "uk", "name": "Ukrainian", "deepl": "UK", "happyscribe": "uk", "elevenlabs": "uk"},
    {"code": "ru", "name": "Russian", "deepl": "RU", "happyscribe": "ru", "elevenlabs": "ru"},
    {"code": "ta", "name": "Tamil", "deepl": "TA", "happyscribe": "ta", "elevenlabs": "ta"},
    {"code": "fil", "name": "Filipino", "deepl": "FIL", "happyscribe": "fil", "elevenlabs": "fil"},
    {"code": "ms", "name": "Malay", "deepl": "MS", "happyscribe": "ms", "elevenlabs": "ms"},
    {"code": "vi", "name": "Vietnamese", "deepl": "VI", "happyscribe": "vi", "elevenlabs": "vi"},
    {"code": "hu", "name": "Hungarian", "deepl": "HU", "happyscribe": "hu", "elevenlabs": "hu"},
    {"code": "nb", "name": "Norwegian", "deepl": "NB", "happyscribe": "nb", "elevenlabs": "nb"},
    {"code": "sw", "name": "Kiswahili", "deepl": "SW", "happyscribe": "sw", "elevenlabs": "sw"},
    {"code": "ha", "name": "Hausa", "deepl": "HA", "happyscribe": "ha", "elevenlabs": "ha"},
]


def get_language(code: str) -> dict | None:
    for lang in SUPPORTED_LANGUAGES:
        if lang["code"] == code:
            return lang
    return None
