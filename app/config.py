from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://leadgen:leadgen@localhost:5432/leadgen"
    redis_url: str = "redis://localhost:6379/0"
    text_generator_provider: str = "template"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    public_base_url: str = "http://localhost:8080"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
