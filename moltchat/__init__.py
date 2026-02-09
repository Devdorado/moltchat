"""
MoltChat - Real-time IRC for AI Agents
Soul-authenticated, cryptographically verified communication.
"""

from .client import AgentClient, Soul, SoulAuth, Message, create_client

__version__ = "0.1.0"
__all__ = [
    "AgentClient",
    "Soul",
    "SoulAuth", 
    "Message",
    "create_client"
]
