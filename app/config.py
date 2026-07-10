from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://leadgen:leadgen@localhost:5432/leadgen"
    redis_url: str = "redis://localhost:6379/0"
    text_generator_provider: str = "template"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    public_base_url: str = "http://localhost:8080"

    deployment_provider: str = "mock"
    cloudflare_api_token: str = ""
    cloudflare_account_id: str = ""
    cloudflare_pages_project: str = "leadgen-agent"
    cloudflare_pages_branch: str = "master"
    cloudflare_public_url: str = "https://leadgen-agent.pages.dev"

    collector_provider: str = "mock"

    two_gis_api_key: str = ""
    two_gis_api_url: str = "https://catalog.api.2gis.com/3.0/items"
    two_gis_city_id: str = ""
    two_gis_page_size: int = 20
    two_gis_max_retries: int = 3
    two_gis_retry_delay: float = 1.0

    csv_file_path: str = "import/companies.csv"
    csv_page_size: int = 20

    verification_enabled: bool = True
    verification_timeout: float = 5.0
    verification_max_redirects: int = 3
    verification_user_agent: str = "LeadGenBot/1.0"

    lead_min_score: int = 50
    lead_score_phone: int = 20
    lead_score_website: int = -30
    lead_score_instagram: int = 15
    lead_score_rating: int = 20
    lead_score_reviews: int = 15

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
