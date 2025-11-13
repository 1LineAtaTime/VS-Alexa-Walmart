"""Configuration management using Pydantic."""

import os
import sys
from pathlib import Path
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings


# Add project root to path for credentials import
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Try to import credentials
try:
    from credentials import credentials
    CREDENTIALS_LOADED = True
except ImportError:
    print("WARNING: credentials/credentials.py not found!")
    print("Please copy credentials/credentials.py.example to credentials/credentials.py")
    print("and fill in your actual credentials.")
    CREDENTIALS_LOADED = False
    # Create dummy credentials object for type checking
    class credentials:
        AMAZON_EMAIL = ""
        AMAZON_PASSWORD = ""
        AMAZON_OTP_SECRET = ""
        WALMART_EMAIL = ""
        WALMART_PASSWORD = ""


class Settings(BaseSettings):
    """Application settings."""

    # Environment
    environment: Literal["development", "production"] = Field(
        default="production",
        description="Runtime environment"
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="DEBUG",
        description="Logging level"
    )
    log_dir: str = Field(
        default="logs",
        description="Directory for log files"
    )

    # Amazon credentials
    amazon_email: str = Field(
        default=credentials.AMAZON_EMAIL,
        description="Amazon account email"
    )
    amazon_password: str = Field(
        default=credentials.AMAZON_PASSWORD,
        description="Amazon account password"
    )
    amazon_otp_secret: str = Field(
        default=credentials.AMAZON_OTP_SECRET,
        description="Amazon OTP secret key"
    )

    # Walmart credentials
    walmart_email: str = Field(
        default=credentials.WALMART_EMAIL,
        description="Walmart account email"
    )
    walmart_password: str = Field(
        default=credentials.WALMART_PASSWORD,
        description="Walmart account password"
    )

    # Browser settings
    browser_headless: bool = Field(
        default=True,  # Set to True for production (headless). Use --headed flag or APP_BROWSER_HEADLESS=false for debugging
        description="Run browser in headless mode"
    )
    browser_timeout: int = Field(
        default=30000,
        description="Browser timeout in milliseconds"
    )

    # Session settings
    cookies_dir: str = Field(
        default="credentials",
        description="Directory for storing session cookies"
    )
    amazon_cookies_file: str = Field(
        default="credentials/amazon_cookies.json",
        description="Amazon session cookies file"
    )
    walmart_cookies_file: str = Field(
        default="credentials/walmart_cookies.json",
        description="Walmart session cookies file"
    )

    # Walmart search settings
    max_search_pages: int = Field(
        default=3,
        description="Maximum pages to search on Walmart"
    )
    search_delay: float = Field(
        default=1.0,
        description="Delay between searches in seconds"
    )

    # Matching settings
    min_match_score: int = Field(
        default=30,
        description="Minimum fuzzy match score (0-100)"
    )
    prefer_frequent_items: bool = Field(
        default=True,
        description="Prefer frequently bought items"
    )

    # Scheduling settings
    schedule_interval_minutes: int = Field(
        default=3,
        description="Interval between runs in minutes (deprecated - use min/max)"
    )
    schedule_interval_min_minutes: int = Field(
        default=3,
        description="Minimum interval between runs in minutes"
    )
    schedule_interval_max_minutes: int = Field(
        default=5,
        description="Maximum interval between runs in minutes"
    )

    # Amazon URLs
    amazon_base_url: str = Field(
        default="https://www.amazon.com",
        description="Amazon base URL"
    )
    amazon_signin_url: str = Field(
        default="https://www.amazon.com/ap/signin",
        description="Amazon sign-in URL"
    )
    amazon_list_url: str = Field(
        default="https://www.amazon.com/gp/alexa-shopping-list",
        description="Amazon Alexa shopping list URL"
    )

    # Walmart URLs
    walmart_base_url: str = Field(
        default="https://www.walmart.com",
        description="Walmart base URL"
    )
    walmart_signin_url: str = Field(
        default="https://www.walmart.com/account/login",
        description="Walmart sign-in URL"
    )

    class Config:
        """Pydantic configuration."""
        env_prefix = "APP_"
        case_sensitive = False


# Global settings instance
settings = Settings()


# Validate credentials are loaded
if not CREDENTIALS_LOADED:
    print("\n" + "="*60)
    print("ERROR: Credentials not configured!")
    print("="*60)
    print("Please follow these steps:")
    print("1. Copy credentials/credentials.py.example to credentials/credentials.py")
    print("2. Edit credentials/credentials.py with your actual credentials")
    print("3. Re-run the application")
    print("="*60 + "\n")
