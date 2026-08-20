from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    FOUNDRY_BASE_URL: str
    CHAT_MODEL: str

    EMBED_APP_NAME: str
    EMBED_MODEL_ALIAS: str
    EMBED_VARIANT_DEVICE: str = "cpu"
    EMBED_DIM: int

    CHROMA_DIR: str = "./data/chroma"
    UPLOAD_DIR: str = "./data/uploads"

    CHUNK_SIZE: int = 900
    CHUNK_OVERLAP: int = 150
    TOP_K: int = 3
    SIMILARITY_THRESHOLD: float = 0.5

    TEMPERATURE_GENERAL: float = 0.7
    TEMPERATURE_RAG: float = 0.2
    MAX_TOKENS: int = 512

    DEBUG_LOG: bool = True

    @property
    def chroma_path(self) -> Path:
        path = (BACKEND_DIR / self.CHROMA_DIR).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def upload_path(self) -> Path:
        path = (BACKEND_DIR / self.UPLOAD_DIR).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
