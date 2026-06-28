"""
Ollama Service
Handles communication with the local Ollama server.
"""

import httpx

from app.core.config import settings
from app.core.logging import logger


class OllamaService:
    """Service for communicating with Ollama."""

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL

    async def health_check(self) -> bool:
        """Check whether Ollama is running."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Ollama Health Check Failed: {e}")
            return False

    async def generate(self, prompt: str) -> str:
        """Generate a response using Ollama."""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                )

                response.raise_for_status()

                data = response.json()

                logger.info("Ollama response generated successfully.")

                return data.get("response", "")

        except Exception as e:
            logger.exception("Ollama Generate Error")
            raise RuntimeError(str(e))


ollama_service = OllamaService()