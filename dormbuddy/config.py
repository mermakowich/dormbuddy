from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    session_secret: SecretStr = Field(min_length=32)
    cookie_secure: bool = False
    buddy_base_url: str = "https://api.openai.com/v1"
    buddy_model: str = "gpt-4o-mini"
    buddy_api_key: SecretStr = SecretStr("")
    buddy_timeout: float = Field(default=20, gt=0, le=120)

    @model_validator(mode="after")
    def check_session_secret(self):
        if self.session_secret.get_secret_value().startswith("demo-placeholder"):
            raise ValueError("Replace the SESSION_SECRET placeholder with a random secret")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
