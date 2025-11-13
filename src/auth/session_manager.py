"""Session manager for cookie persistence and validation."""

import json
from pathlib import Path
from typing import Dict, List, Optional
from playwright.sync_api import BrowserContext, Page
from loguru import logger


class SessionManager:
    """Manages browser sessions with cookie persistence."""

    def __init__(self, cookies_file: str):
        """Initialize session manager.

        Args:
            cookies_file: Path to cookies JSON file
        """
        self.cookies_file = Path(cookies_file)
        self.cookies_file.parent.mkdir(parents=True, exist_ok=True)

    def save_cookies(self, context: BrowserContext) -> None:
        """Save cookies from browser context to file.

        Args:
            context: Playwright browser context
        """
        try:
            cookies = context.cookies()
            with open(self.cookies_file, "w") as f:
                json.dump(cookies, f, indent=2)
            logger.info(f"Saved {len(cookies)} cookies to {self.cookies_file}")
        except Exception as e:
            logger.error(f"Failed to save cookies: {e}")

    def load_cookies(self, context: BrowserContext) -> bool:
        """Load cookies from file into browser context.

        Args:
            context: Playwright browser context

        Returns:
            True if cookies were loaded successfully
        """
        try:
            if not self.cookies_file.exists():
                logger.info("No existing cookies file found")
                return False

            with open(self.cookies_file, "r") as f:
                cookies = json.load(f)

            if not cookies:
                logger.warning("Cookies file is empty")
                return False

            context.add_cookies(cookies)
            logger.success(f"Loaded {len(cookies)} cookies from {self.cookies_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to load cookies: {e}")
            return False

    def cookies_exist(self) -> bool:
        """Check if cookies file exists.

        Returns:
            True if cookies file exists
        """
        return self.cookies_file.exists()

    def clear_cookies(self) -> None:
        """Delete cookies file."""
        try:
            if self.cookies_file.exists():
                self.cookies_file.unlink()
                logger.info(f"Deleted cookies file: {self.cookies_file}")
        except Exception as e:
            logger.error(f"Failed to delete cookies: {e}")

    def validate_session(
        self,
        page: Page,
        check_url: str,
        validation_selector: str,
        timeout: int = 5000
    ) -> bool:
        """Validate that a session is still active.

        Args:
            page: Playwright page
            check_url: URL to check for session validity
            validation_selector: CSS selector to check for logged-in state
            timeout: Timeout in milliseconds

        Returns:
            True if session is valid
        """
        try:
            logger.info(f"Validating session at {check_url}")
            page.goto(check_url, timeout=timeout, wait_until="domcontentloaded")

            # Check if we're still logged in by looking for a logged-in element
            try:
                page.wait_for_selector(validation_selector, timeout=timeout)
                logger.success("Session is valid")
                return True
            except Exception:
                logger.warning("Session validation failed - element not found")
                return False

        except Exception as e:
            logger.error(f"Session validation error: {e}")
            return False
