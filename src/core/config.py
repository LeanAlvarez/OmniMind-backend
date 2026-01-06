"""configuration management using pydantic-settings."""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """application settings loaded from environment variables."""

    # openrouter configuration
    openrouter_api_key: str
    model_name: str = "openai/gpt-4o-mini"
    
    # supabase configuration
    supabase_project_url: Optional[str] = None
    supabase_anon_public: Optional[str] = None
    supabase_service_role: Optional[str] = None
    
    @property
    def supabase_url(self) -> Optional[str]:
        """get supabase url from project url."""
        return self.supabase_project_url
    
    @property
    def supabase_key(self) -> Optional[str]:
        """get supabase key, prefer service_role over anon_public."""
        return self.supabase_service_role or self.supabase_anon_public
    
    # n8n webhook configuration (optional)
    n8n_webhook_url: Optional[str] = None
    
    # search tool configuration (optional)
    tavily_api_key: Optional[str] = None
    
    # application configuration
    app_name: str = "omnimind-backend"
    app_version: str = "0.1.0"
    debug: bool = False
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# global settings instance
settings = Settings()

