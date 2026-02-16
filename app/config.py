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

    # Auth
    admin_email: str = "admin@aipod.local"
    admin_password: str = "changeme123"
    session_cookie_name: str = "aipod_session"
    session_max_age: int = 604800  # 7 days

    model_config = {"env_file": str(BASE_DIR / ".env"), "env_file_encoding": "utf-8"}


settings = Settings()

# --- Supported Languages (single source of truth) ---
# Codes match Google Translate (used by deep-translator)
SUPPORTED_LANGUAGES = [
    # --- Europe ---
    {"code": "en", "name": "English", "deepl": "EN", "happyscribe": "en", "elevenlabs": "en"},
    {"code": "fr", "name": "French", "deepl": "FR", "happyscribe": "fr", "elevenlabs": "fr"},
    {"code": "es", "name": "Spanish", "deepl": "ES", "happyscribe": "es", "elevenlabs": "es"},
    {"code": "pt", "name": "Portuguese (BR)", "deepl": "PT-BR", "happyscribe": "pt-BR", "elevenlabs": "pt"},
    {"code": "de", "name": "German", "deepl": "DE", "happyscribe": "de", "elevenlabs": "de"},
    {"code": "it", "name": "Italian", "deepl": "IT", "happyscribe": "it", "elevenlabs": "it"},
    {"code": "nl", "name": "Dutch", "deepl": "NL", "happyscribe": "nl", "elevenlabs": "nl"},
    {"code": "pl", "name": "Polish", "deepl": "PL", "happyscribe": "pl", "elevenlabs": "pl"},
    {"code": "sv", "name": "Swedish", "deepl": "SV", "happyscribe": "sv", "elevenlabs": "sv"},
    {"code": "da", "name": "Danish", "deepl": "DA", "happyscribe": "da", "elevenlabs": "da"},
    {"code": "nb", "name": "Norwegian", "deepl": "NB", "happyscribe": "nb", "elevenlabs": "nb"},
    {"code": "fi", "name": "Finnish", "deepl": "FI", "happyscribe": "fi", "elevenlabs": "fi"},
    {"code": "el", "name": "Greek", "deepl": "EL", "happyscribe": "el", "elevenlabs": "el"},
    {"code": "cs", "name": "Czech", "deepl": "CS", "happyscribe": "cs", "elevenlabs": "cs"},
    {"code": "sk", "name": "Slovak", "deepl": "SK", "happyscribe": "sk", "elevenlabs": "sk"},
    {"code": "ro", "name": "Romanian", "deepl": "RO", "happyscribe": "ro", "elevenlabs": "ro"},
    {"code": "bg", "name": "Bulgarian", "deepl": "BG", "happyscribe": "bg", "elevenlabs": "bg"},
    {"code": "hr", "name": "Croatian", "deepl": "HR", "happyscribe": "hr", "elevenlabs": "hr"},
    {"code": "hu", "name": "Hungarian", "deepl": "HU", "happyscribe": "hu", "elevenlabs": "hu"},
    {"code": "uk", "name": "Ukrainian", "deepl": "UK", "happyscribe": "uk", "elevenlabs": "uk"},
    {"code": "ru", "name": "Russian", "deepl": "RU", "happyscribe": "ru", "elevenlabs": "ru"},
    {"code": "tr", "name": "Turkish", "deepl": "TR", "happyscribe": "tr", "elevenlabs": "tr"},
    # --- Asia & Middle East ---
    {"code": "ar", "name": "Arabic", "deepl": "AR", "happyscribe": "ar", "elevenlabs": "ar"},
    {"code": "zh", "name": "Chinese (Mandarin)", "deepl": "ZH", "happyscribe": "zh", "elevenlabs": "zh"},
    {"code": "hi", "name": "Hindi", "deepl": "HI", "happyscribe": "hi", "elevenlabs": "hi"},
    {"code": "ja", "name": "Japanese", "deepl": "JA", "happyscribe": "ja", "elevenlabs": "ja"},
    {"code": "ko", "name": "Korean", "deepl": "KO", "happyscribe": "ko", "elevenlabs": "ko"},
    {"code": "vi", "name": "Vietnamese", "deepl": "VI", "happyscribe": "vi", "elevenlabs": "vi"},
    {"code": "id", "name": "Indonesian", "deepl": "ID", "happyscribe": "id", "elevenlabs": "id"},
    {"code": "ms", "name": "Malay", "deepl": "MS", "happyscribe": "ms", "elevenlabs": "ms"},
    {"code": "fil", "name": "Filipino", "deepl": "FIL", "happyscribe": "fil", "elevenlabs": "fil"},
    {"code": "ta", "name": "Tamil", "deepl": "TA", "happyscribe": "ta", "elevenlabs": "ta"},
    {"code": "bn", "name": "Bengali", "deepl": "BN", "happyscribe": "bn", "elevenlabs": "bn"},
    {"code": "ur", "name": "Urdu", "deepl": "UR", "happyscribe": "ur", "elevenlabs": "ur"},
    {"code": "th", "name": "Thai", "deepl": "TH", "happyscribe": "th", "elevenlabs": "th"},
    # --- African ---
    {"code": "sw", "name": "Swahili", "deepl": "SW", "happyscribe": "sw", "elevenlabs": "sw"},
    {"code": "ha", "name": "Hausa", "deepl": "HA", "happyscribe": "ha", "elevenlabs": "ha"},
    {"code": "yo", "name": "Yoruba", "deepl": "YO", "happyscribe": "yo", "elevenlabs": "yo"},
    {"code": "ig", "name": "Igbo", "deepl": "IG", "happyscribe": "ig", "elevenlabs": "ig"},
    {"code": "zu", "name": "Zulu", "deepl": "ZU", "happyscribe": "zu", "elevenlabs": "zu"},
    {"code": "xh", "name": "Xhosa", "deepl": "XH", "happyscribe": "xh", "elevenlabs": "xh"},
    {"code": "af", "name": "Afrikaans", "deepl": "AF", "happyscribe": "af", "elevenlabs": "af"},
    {"code": "am", "name": "Amharic", "deepl": "AM", "happyscribe": "am", "elevenlabs": "am"},
    {"code": "so", "name": "Somali", "deepl": "SO", "happyscribe": "so", "elevenlabs": "so"},
    {"code": "rw", "name": "Kinyarwanda", "deepl": "RW", "happyscribe": "rw", "elevenlabs": "rw"},
    {"code": "sn", "name": "Shona", "deepl": "SN", "happyscribe": "sn", "elevenlabs": "sn"},
    {"code": "ny", "name": "Chichewa", "deepl": "NY", "happyscribe": "ny", "elevenlabs": "ny"},
    {"code": "mg", "name": "Malagasy", "deepl": "MG", "happyscribe": "mg", "elevenlabs": "mg"},
    {"code": "st", "name": "Sesotho", "deepl": "ST", "happyscribe": "st", "elevenlabs": "st"},
    {"code": "tn", "name": "Setswana", "deepl": "TN", "happyscribe": "tn", "elevenlabs": "tn"},
    {"code": "ts", "name": "Tsonga", "deepl": "TS", "happyscribe": "ts", "elevenlabs": "ts"},
    {"code": "lg", "name": "Luganda", "deepl": "LG", "happyscribe": "lg", "elevenlabs": "lg"},
    {"code": "om", "name": "Oromo", "deepl": "OM", "happyscribe": "om", "elevenlabs": "om"},
    {"code": "ti", "name": "Tigrinya", "deepl": "TI", "happyscribe": "ti", "elevenlabs": "ti"},
    {"code": "ln", "name": "Lingala", "deepl": "LN", "happyscribe": "ln", "elevenlabs": "ln"},
    {"code": "ak", "name": "Twi (Akan)", "deepl": "AK", "happyscribe": "ak", "elevenlabs": "ak"},
    {"code": "wo", "name": "Wolof", "deepl": "WO", "happyscribe": "wo", "elevenlabs": "wo"},
    {"code": "nso", "name": "Sepedi", "deepl": "NSO", "happyscribe": "nso", "elevenlabs": "nso"},
    {"code": "ee", "name": "Ewe", "deepl": "EE", "happyscribe": "ee", "elevenlabs": "ee"},
    {"code": "bm", "name": "Bambara", "deepl": "BM", "happyscribe": "bm", "elevenlabs": "bm"},
]


# Grouped for UI dropdowns (continent-based, no repetition)
LANGUAGE_GROUPS = [
    ("Europe", [l for l in SUPPORTED_LANGUAGES if l["code"] in (
        "en", "fr", "es", "pt", "de", "it", "nl", "pl", "sv", "da", "nb", "fi",
        "el", "cs", "sk", "ro", "bg", "hr", "hu", "uk", "ru", "tr",
    )]),
    ("Asia & Middle East", [l for l in SUPPORTED_LANGUAGES if l["code"] in (
        "ar", "zh", "hi", "ja", "ko", "vi", "id", "ms", "fil", "ta", "bn", "ur", "th",
    )]),
    ("Africa", [l for l in SUPPORTED_LANGUAGES if l["code"] in (
        "sw", "ha", "yo", "ig", "zu", "xh", "af", "am", "so", "rw", "sn", "ny", "mg", "st", "tn", "ts",
        "lg", "om", "ti", "ln", "ak", "wo", "nso", "ee", "bm",
    )]),
]


def get_language(code: str) -> dict | None:
    for lang in SUPPORTED_LANGUAGES:
        if lang["code"] == code:
            return lang
    return None
