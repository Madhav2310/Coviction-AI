"""

Coviction Configuration — Single source of truth for all settings.

Adapted from ThesisOS, stripped to MVP essentials.

"""

import logging

from pydantic_settings import BaseSettings

from pydantic import Field, model_validator

from functools import lru_cache

from typing import Optional



_config_logger = logging.getLogger(__name__)





class Settings(BaseSettings):

    """All configuration loaded from environment variables."""



    # -- Database --

    database_url: str = Field(

        default="postgresql+asyncpg://madhmitt@localhost:5432/coviction",

        description="Async Postgres connection string"

    )
    db_pool_size: int = Field(default=3, description="Base Postgres connection pool size")
    db_max_overflow: int = Field(default=2, description="Temporary overflow DB connections")



    # -- Auth --

    jwt_secret: str = Field(default="coviction-dev-secret-change-in-production")

    jwt_algorithm: str = Field(default="HS256")

    jwt_expiry_hours: int = Field(default=72)



    # -- LLM Models --

    openai_api_key: str = Field(default="")

    openai_base_url: Optional[str] = Field(default=None, description="Override for proxied OpenAI")

    default_strong_model: str = Field(default="gpt-4o-mini")

    default_fast_model: str = Field(default="gpt-4o-mini")

    entity_extraction_model: str = Field(default="gpt-4o-mini")

    default_embedding_model: str = Field(default="text-embedding-3-small")

    embedding_dimensions: int = Field(default=1536)



    # -- SSL/Certs --

    genai_ca_cert: str = Field(default="", description="Path to CA cert for GenAI proxy")



    # -- Whisper --

    whisper_model: str = Field(default="whisper-1")



    # -- App --

    app_name: str = Field(default="Coviction")

    debug: bool = Field(default=True)

    cors_origins: list[str] = Field(default=["http://localhost:3000", "http://localhost:8000", "http://localhost:8081", "http://127.0.0.1:5500", "null", "*"])



    @model_validator(mode="after")

    def _warn_insecure_jwt_secret(self) -> "Settings":

        if "dev-secret" in self.jwt_secret:

            _config_logger.warning("JWT_SECRET is set to dev default. Change before deploying.")

        return self



    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}





@lru_cache

def get_settings() -> Settings:

    return Settings()
