from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://leadgen:leadgen@localhost:5432/leadgen"
    redis_url: str = "redis://localhost:6379/0"
    text_generator_provider: str = "template"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: int = 45
    openai_max_retries: int = 3
    openai_temperature: float = 0.4
    openai_max_output_tokens: int = 2500
    openai_daily_budget_usd: float = 5.0
    openai_max_requests_per_job: int = 30
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

    default_language: str = "ru"

    admin_username: str = "admin"
    admin_password: str = ""

    outreach_provider: str = "mock"
    outreach_enabled: bool = False
    outreach_max_per_hour: int = 20
    outreach_quiet_hours_start: str = "20:00"
    outreach_quiet_hours_end: str = "09:00"
    outreach_timezone: str = "Asia/Almaty"
    outreach_max_message_length: int = 1000

    whatsapp_cloud_api_token: str = ""
    whatsapp_cloud_phone_number_id: str = ""
    whatsapp_cloud_business_account_id: str = ""
    whatsapp_webhook_verify_token: str = ""

    email_smtp_host: str = ""
    email_smtp_port: int = 587
    email_smtp_user: str = ""
    email_smtp_password: str = ""
    email_from_address: str = ""
    email_from_name: str = "LeadGen"

    telegram_bot_token: str = ""

    follow_up_enabled: bool = True
    follow_up_delay_hours: int = 48
    follow_up_max_count: int = 2

    @model_validator(mode="after")
    def validate_openai_config(self) -> "Settings":
        if self.text_generator_provider == "openai":
            if not self.openai_api_key:
                raise ValueError(
                    "OPENAI_API_KEY is required when TEXT_GENERATOR_PROVIDER=openai"
                )
            if not self.openai_model:
                raise ValueError(
                    "OPENAI_MODEL is required when TEXT_GENERATOR_PROVIDER=openai"
                )
        if self.openai_timeout_seconds <= 0:
            raise ValueError("OPENAI_TIMEOUT_SECONDS must be positive")
        if self.openai_max_retries < 0:
            raise ValueError("OPENAI_MAX_RETRIES must be non-negative")
        if self.openai_daily_budget_usd < 0:
            raise ValueError("OPENAI_DAILY_BUDGET_USD must be non-negative")
        if self.openai_max_requests_per_job < 0:
            raise ValueError("OPENAI_MAX_REQUESTS_PER_JOB must be non-negative")
        return self

    @model_validator(mode="after")
    def validate_admin_password(self) -> "Settings":
        if self.app_env == "production" and not self.admin_password:
            raise ValueError("ADMIN_PASSWORD is required in production mode")
        return self

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
