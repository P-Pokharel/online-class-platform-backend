from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str

    jwt_secret_key: str = Field(min_length=32)
    access_token_expire_minutes: int = 60
    cookie_secure: bool = True
    cors_origins: list[str] = ["http://localhost:3000"]

    admin_email: str | None = None
    admin_password: str | None = None
    admin_full_name: str = "Administrator"


settings = Settings()
