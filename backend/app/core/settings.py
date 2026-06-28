# backend/app/core/settings.py

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Base settings for Rabeeh AI Agent Pro."""
    
    APP_NAME: str = "Rabeeh AI Agent Pro"
    VERSION: str = "1.1"
    OLLAMA_URL: str = "http://localhost:11434"
    DEFAULT_MODEL: str = "qwen2.5-coder:7b"

    class Config:
        """Configuration for settings."""
        
        env_file = ".env"  # Optional: Load environment variables from .env file

settings = Settings()