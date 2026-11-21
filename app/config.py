"""
app/config.py - Application configuration using pydantic-settings.
Loads from environment variables and .env file.
"""

from typing import List, Optional, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # LLM Providers & Keys
    DEFAULT_LLM_PROVIDER: str = "gemini"  # "gemini", "groq", "openai", "mock"
    GEMINI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # Agent Models
    SCHEMA_AGENT_MODEL: str = "gemini-3.1-flash-lite"
    SQL_WRITER_MODEL: str = "gemini-3.1-flash-lite"
    EXPLAINER_MODEL: str = "gemini-3.1-flash-lite"

    # Agent Temperatures
    SCHEMA_AGENT_TEMPERATURE: float = 0.0
    SQL_WRITER_TEMPERATURE: float = 0.0
    EXPLAINER_TEMPERATURE: float = 0.2

    # Database & MCP
    DATABASE_PATH: str = "data/sample.db"
    MCP_SERVER_COMMAND: str = "python app/mcp_server/server.py"
    QUERY_TIMEOUT_SECONDS: float = 10.0
    MAX_ROW_CAP: int = 1000
    DEFAULT_QUERY_LIMIT: int = 100

    # LangGraph
    MAX_RETRIES: int = 3

    # Guardrails
    ENABLE_MASKING: bool = True
    SENSITIVE_COLUMNS: Union[List[str], str] = Field(default_factory=lambda: ["customers.email", "customers.phone"])

    # Observability
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    @field_validator("SENSITIVE_COLUMNS", mode="after")
    @classmethod
    def parse_sensitive_columns(cls, v):
        if isinstance(v, str):
            return [col.strip() for col in v.split(",") if col.strip()]
        return v


# Global singleton settings instance
settings = Settings()
