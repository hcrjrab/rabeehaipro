"""
Rabeeh AI Agent
Coordinates AI interactions using the Ollama service.
"""

from app.core.logging import logger
from app.services.ollama_service import ollama_service


class RabeehAgent:
    """Main AI Agent."""

    def __init__(self):
        self.name = "Rabeeh AI"
        self.version = "1.0.0"

    async def chat(self, prompt: str) -> str:
        """
        Send a prompt to the AI model.
        """

        logger.info("Received prompt.")

        if not prompt.strip():
            return "Prompt cannot be empty."

        response = await ollama_service.generate(prompt)

        logger.info("Response generated.")

        return response

    async def health(self) -> bool:
        """Check Ollama availability."""
        return await ollama_service.health_check()


agent = RabeehAgent()