"""
Conversation Memory for Rabeeh AI.
Stores chat history in memory.
"""

from collections import deque
from typing import Dict, List


class ConversationMemory:
    """Simple in-memory conversation storage."""

    def __init__(self, max_messages: int = 20):
        self.max_messages = max_messages
        self.sessions: Dict[str, deque] = {}

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> None:

        if session_id not in self.sessions:
            self.sessions[session_id] = deque(maxlen=self.max_messages)

        self.sessions[session_id].append(
            {
                "role": role,
                "content": content,
            }
        )

    def get_history(
        self,
        session_id: str,
    ) -> List[dict]:

        if session_id not in self.sessions:
            return []

        return list(self.sessions[session_id])

    def clear(
        self,
        session_id: str,
    ) -> None:

        self.sessions.pop(session_id, None)


memory = ConversationMemory()