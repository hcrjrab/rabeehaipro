"""
Chat API Schemas.
"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    success: bool
    response: str