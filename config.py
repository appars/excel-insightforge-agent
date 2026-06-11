"""
Configuration management for Excel InsightForge Agent.

Implements the hybrid API key strategy:
    1. Sidebar-entered API key (session)
    2. .env file
    3. Environment variable
    4. Analytics Mode fallback (no key)
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

# Load .env if present (no-op otherwise)
load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("insightforge")

APP_NAME = "Excel InsightForge Agent"
APP_SUBTITLE = "AI-Ready Analytics Platform"
GROQ_MODEL = "llama-3.3-70b-versatile"
PROVIDER = "Groq"


@dataclass(frozen=True)
class AIConfig:
    """Resolved AI configuration for the current session."""

    api_key: Optional[str]
    provider: str = PROVIDER
    model: str = GROQ_MODEL

    @property
    def ai_enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def mode(self) -> str:
        return "AI Mode" if self.ai_enabled else "Analytics Mode"


def resolve_api_key(sidebar_key: Optional[str] = None) -> AIConfig:
    """Resolve the Groq API key using the hybrid priority strategy.

    Args:
        sidebar_key: Key typed in the Streamlit sidebar (highest priority).

    Returns:
        AIConfig with the resolved key (or None -> Analytics Mode).
    """
    key = (sidebar_key or "").strip() or os.getenv("GROQ_API_KEY", "").strip() or None
    if key:
        logger.info("AI Mode enabled (provider=%s, model=%s)", PROVIDER, GROQ_MODEL)
    else:
        logger.info("No API key found — running in Analytics Mode")
    return AIConfig(api_key=key)
