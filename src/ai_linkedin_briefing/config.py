from __future__ import annotations

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-5.4", alias="OPENAI_MODEL")
    openai_timeout_seconds: int = Field(default=120, alias="OPENAI_TIMEOUT_SECONDS")
    linkedin_email: Optional[str] = Field(default=None, alias="LINKEDIN_EMAIL")
    linkedin_password: Optional[str] = Field(default=None, alias="LINKEDIN_PASSWORD")
    linkedin_keychain_service: str = Field(
        default="ai-linkedin-briefing/linkedin",
        alias="LINKEDIN_KEYCHAIN_SERVICE",
    )
    linkedin_browser_state_path: Path = Field(
        default=PROJECT_ROOT / "secrets" / "linkedin_state.json",
        alias="LINKEDIN_BROWSER_STATE_PATH",
    )
    timezone: str = Field(default="America/Los_Angeles", alias="TIMEZONE")
    publish_hour: int = Field(default=8, alias="PUBLISH_HOUR")
    author_name: str = Field(default="Djay Pandya", alias="AUTHOR_NAME")
    summarizer_backend: str = Field(default="openai", alias="SUMMARIZER_BACKEND")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="deepseek-r1:70b", alias="OLLAMA_MODEL")
    ollama_timeout_seconds: int = Field(default=120, alias="OLLAMA_TIMEOUT_SECONDS")
    article_fetch_timeout_seconds: int = Field(default=20, alias="ARTICLE_FETCH_TIMEOUT_SECONDS")


class DocumentPaths(BaseModel):
    model_config = ConfigDict(frozen=True)

    newsletter_template: Path
    source_criteria: Path
    agent_spec: Path
    output_dir: Path
    log_dir: Path


def load_config() -> AppConfig:
    load_dotenv(PROJECT_ROOT / ".env")
    return AppConfig()


def build_document_paths() -> DocumentPaths:
    return DocumentPaths(
        newsletter_template=PROJECT_ROOT / "newsletter_template.md",
        source_criteria=PROJECT_ROOT / "source_criteria.md",
        agent_spec=PROJECT_ROOT / "agent_spec.md",
        output_dir=PROJECT_ROOT / "output",
        log_dir=PROJECT_ROOT / "logs",
    )
