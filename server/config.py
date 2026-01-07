"""Server configuration using pydantic-settings"""

from pydantic_settings import BaseSettings
from typing import Literal
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Environment
    env: Literal["development", "production"] = "development"
    debug: bool = True

    # Provider mode
    provider_mode: Literal["mock", "live"] = "mock"

    # Storage
    artifact_dir: str = "/artifacts"

    # API Keys (loaded from .env or environment)
    anthropic_api_key: str = ""
    runway_api_key: str = ""
    elevenlabs_api_key: str = ""
    openai_api_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
