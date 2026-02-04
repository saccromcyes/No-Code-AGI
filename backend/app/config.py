import os
from pydantic import BaseModel


class Settings(BaseModel):
    api_title: str = "OpenAGI Assistant Builder API"
    api_description: str = "Backend services for managing assistants, workflows, and users."
    api_version: str = "1.0.0"
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./openagi.db")
    cors_origins: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    environment: str = os.getenv("APP_ENV", "development")


settings = Settings()
