from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProviderSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_", extra="ignore")

    api_key: SecretStr = Field(default=SecretStr(""))
    model: str = Field(default="gpt-4o")
    base_url: str = Field(default="")


class OpenAISettings(LLMProviderSettings):
    model_config = SettingsConfigDict(env_prefix="OPENAI_", extra="ignore")

    api_key: SecretStr = Field(default=SecretStr(""))
    model: str = Field(default="gpt-4o")
    base_url: str = Field(default="https://api.openai.com/v1")


class AnthropicSettings(LLMProviderSettings):
    model_config = SettingsConfigDict(env_prefix="ANTHROPIC_", extra="ignore")

    api_key: SecretStr = Field(default=SecretStr(""))
    model: str = Field(default="claude-sonnet-4-20250514")
    base_url: str = Field(default="https://api.anthropic.com")


class OllamaSettings(LLMProviderSettings):
    model_config = SettingsConfigDict(env_prefix="OLLAMA_", extra="ignore")

    api_key: SecretStr = Field(default=SecretStr(""))
    model: str = Field(default="llama3")
    base_url: str = Field(default="http://localhost:11434")


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DB_", extra="ignore")

    async_url: str = Field(default="postgresql+asyncpg://nexusforge:nexusforge@localhost:5432/nexusforge")
    sync_url: str = Field(default="postgresql://nexusforge:nexusforge@localhost:5432/nexusforge")
    echo: bool = Field(default=False)
    pool_size: int = Field(default=20)
    max_overflow: int = Field(default=10)
    pool_pre_ping: bool = Field(default=True)


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_", extra="ignore")

    url: str = Field(default="redis://localhost:6379/0")
    max_connections: int = Field(default=50)


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", extra="ignore")

    secret_key: SecretStr = Field(default_factory=lambda: SecretStr(secrets.token_urlsafe(64)))
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=30)
    refresh_token_expire_days: int = Field(default=7)
    bcrypt_rounds: int = Field(default=12)


class MCPServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCP_", extra="ignore")

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8100)


class ResilienceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RESILIENCE_", extra="ignore")

    max_retries: int = Field(default=3)
    circuit_breaker_threshold: int = Field(default=5)
    circuit_breaker_timeout_seconds: int = Field(default=60)
    budget_limit_usd: float = Field(default=100.0)
    workflow_timeout_seconds: int = Field(default=3600)


class ObservabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OBS_", extra="ignore")

    tracing_enabled: bool = Field(default=True)
    tracing_provider: Literal["otlp", "langsmith", "console", "none"] = Field(default="console")
    langsmith_api_key: SecretStr = Field(default=SecretStr(""))
    langsmith_project: str = Field(default="nexusforge")
    langsmith_endpoint: str = Field(default="https://api.smith.langchain.com")
    metrics_enabled: bool = Field(default=True)
    metrics_port: int = Field(default=9090)


class ConnectorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONNECTOR_", extra="ignore")

    hubspot_token: SecretStr = Field(default=SecretStr(""))
    salesforce_token: SecretStr = Field(default=SecretStr(""))
    jira_token: SecretStr = Field(default=SecretStr(""))
    github_token: SecretStr = Field(default=SecretStr(""))
    slack_token: SecretStr = Field(default=SecretStr(""))
    servicenow_token: SecretStr = Field(default=SecretStr(""))
    sap_url: str = Field(default="")
    ms_graph_token: SecretStr = Field(default=SecretStr(""))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NEXUSFORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="NexusForge")
    version: str = Field(default="0.1.0")
    environment: Literal["development", "staging", "production"] = Field(default="development")
    debug: bool = Field(default=False)
    api_v1_prefix: str = Field(default="/api/v1")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"]
    )

    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    mcp: MCPServerSettings = Field(default_factory=MCPServerSettings)
    resilience: ResilienceSettings = Field(default_factory=ResilienceSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    connectors: ConnectorSettings = Field(default_factory=ConnectorSettings)

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"Environment must be one of {allowed}")
        return v

    def validate_production_posture(self) -> list[str]:
        warnings: list[str] = []
        if self.environment == "production":
            if self.debug:
                warnings.append("DEBUG mode is enabled in production")
            if self.auth.secret_key.get_secret_value() == "":
                warnings.append("AUTH_SECRET_KEY is not set")
            if self.openai.api_key.get_secret_value() == "":
                warnings.append("OPENAI_API_KEY is not set")
            if "localhost" in self.db.async_url:
                warnings.append("Database URL points to localhost in production")
            if "localhost" in self.redis.url:
                warnings.append("Redis URL points to localhost in production")
            if "http://localhost" in self.cors_origins or "http://localhost:3000" in self.cors_origins:
                warnings.append("CORS includes localhost origins in production")
        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()
