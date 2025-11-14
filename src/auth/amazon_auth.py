"""Amazon authentication with OTP support."""

import time
import pyotp
from playwright.sync_api import Page, Browser, BrowserContext, TimeoutError
from loguru import logger

from ..config import settings
from .session_manager import SessionManager


class AmazonAuthenticator:
    """Handles Amazon authentication with OTP."""

    def __init__(self, browser: Browser):
        """Initialize Amazon authenticator.

        Args:
            browser: Playwright browser instance
        """
        self.browser = browser
        self.context: BrowserContext = None
        self.page: Page = None
        self.session_manager = SessionManager(settings.amazon_cookies_file)

    def authenticate(self) -> Page:
        """Authenticate with Amazon and return logged-in page.

        Returns:
            Playwright page with active Amazon session

        Raises:
            Exception: If authentication fails
        """
        # Create browser context
        self.context = self.browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        self.page = self.context.new_page()

        # Try to load existing cookies
        if self.session_manager.cookies_exist():
            logger.info("Found existing Amazon cookies, attempting to use them")
            self.session_manager.load_cookies(self.context)

            # Validate session
            if self._validate_session():
                logger.success("Existing Amazon session is valid!")
                return self.page

            logger.warning("Existing session invalid, logging in again")
            self.session_manager.clear_cookies()

        # Perform fresh login
        self._login()
        return self.page

    def _validate_session(self) -> bool:
        """Validate that current session is active by navigating directly to shopping list.

        If already logged in, we'll see the shopping list.
        If not logged in, Amazon will redirect to sign-in page.

        Returns:
            True if session is valid (on shopping list page)
        """
        try:
            # Navigate directly to the shopping list page
            logger.info("Navigating to shopping list to validate session...")
            self.page.goto("https://www.amazon.com/gp/alexa-shopping-list", wait_until="domcontentloaded")
            time.sleep(3)

            # Check if we're on a sign-in page (password or email field visible)
            try:
                signin_field = self.page.locator("#ap_email, #ap_password, input[type='email'], input[type='password'][name='password']").first
                if signin_field.is_visible(timeout=2000):
                    logger.info("Session invalid - redirected to sign-in page")
                    return False
                else:
                    logger.success("Session valid - on shopping list page")
                    return True
            except:
                # No sign-in fields = we're on the shopping list page
                logger.success("Session valid - on shopping list page")
                return True

        except Exception as e:
            logger.error(f"Session validation failed: {e}")
            return False

    def _login(self) -> None:
        """Perform Amazon login with OTP.

        Navigates directly to Amazon sign-in page with return URL to shopping list.

        Raises:
            Exception: If login fails
        """
        logger.info("Starting Amazon login process")

        try:
            # Navigate directly to Amazon sign-in page with shopping list return URL
            amazon_signin_url = (
                "https://www.amazon.com/ap/signin?"
                "openid.pape.max_auth_age=3600&"
                "openid.return_to=https%3A%2F%2Fwww.amazon.com%2Falexaquantum%2Fsp%2FalexaShoppingList%3Fref_%3Dlist_d_wl_ys_list_1&"
                "openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&"
                "openid.assoc_handle=amzn_alexa_quantum_us&"
                "openid.mode=checkid_setup&"
                "language=en_US&"
                "openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&"
                "openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0"
            )

            logger.info("Navigating to Amazon sign-in page...")
            self.page.goto(amazon_signin_url, wait_until="domcontentloaded")
            time.sleep(2)

            logger.info("On Amazon sign-in page")

            # Enter email
            logger.info("Entering email...")
            email_input = self.page.wait_for_selector("#ap_email, input[type='email']", timeout=10000)
            email_input.fill(settings.amazon_email)

            # Click Continue - use .first to handle multiple matches
            continue_button = self.page.locator("#continue").first
            continue_button.click()
            logger.info("Clicked Continue")

            # Wait for password field
            time.sleep(1)

            # Enter password
            logger.info("Entering password...")
            password_input = self.page.wait_for_selector("#ap_password", timeout=10000)
            password_input.fill(settings.amazon_password)

            # Check "Keep me signed in" checkbox (with short timeout - it might not be here)
            try:
                remember_checkbox = self.page.locator("#rememberMe")
                # Use short timeout to avoid 30-second wait
                if not remember_checkbox.is_checked(timeout=2000):
                    remember_checkbox.check()
                    logger.info("Checked 'Keep me signed in'")
            except Exception:
                # Checkbox not found on password page - might be on OTP page
                pass

            # Click Sign-In and wait for navigation
            signin_button = self.page.locator("#signInSubmit")
            signin_button.click()
            logger.info("Clicked Sign-In")

            # Wait for navigation to complete (to OTP page or success page)
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass  # Page might not navigate, that's okay

            # Give extra time for any redirects or page loads
            time.sleep(3)

            # Debug: Log current URL to see where we are
            logger.info(f"Current URL after sign-in: {self.page.url}")

            # Handle OTP if required
            self._handle_otp()

            # Handle "Not now" for additional security prompts
            self._handle_additional_prompts()

            # Verify we're logged in by navigating to shopping list
            logger.info("Verifying login by accessing shopping list...")
            self.page.goto("https://www.amazon.com/gp/alexa-shopping-list", wait_until="domcontentloaded")
            time.sleep(2)

            # Check if we're still on sign-in page (login failed)
            try:
                password_field = self.page.locator("#ap_password, input[type='password'][name='password']").first
                if password_field.is_visible(timeout=2000):
                    raise Exception("Login failed - still on sign-in page after authentication")
            except TimeoutError:
                pass  # Good - no password field means we're logged in

            # Save cookies for future use
            self.session_manager.save_cookies(self.context)

            logger.success("Amazon login successful and shopping list accessible!")

        except TimeoutError as e:
            logger.error(f"Timeout during Amazon login: {e}")
            self._save_screenshot("amazon_login_timeout")
            raise Exception(f"Amazon login timeout: {e}")

        except Exception as e:
            logger.error(f"Amazon login failed: {e}")
            self._save_screenshot("amazon_login_error")
            raise Exception(f"Amazon login failed: {e}")

    def _handle_otp(self) -> None:
        """Handle OTP verification if requested.

        Raises:
            Exception: If OTP handling fails
        """
        try:
            # Check if we're on the OTP page by URL or selector
            current_url = self.page.url.lower()
            logger.info(f"Checking for OTP requirement (URL: {current_url})")

            # Check if OTP is required - wait longer for page to load
            otp_input = None
            try:
                # Try multiple selectors with longer timeout
                otp_input = self.page.wait_for_selector(
                    "#auth-mfa-otpcode, input[name='otpCode'], input[aria-label*='OTP'], input[aria-label*='code']",
                    timeout=10000
                )
            except TimeoutError:
                # Double-check by URL in case selector changed
                if "mfa" in current_url or "otp" in current_url or "verify" in current_url:
                    logger.warning("OTP page detected by URL but input field not found - taking screenshot")
                    self._save_screenshot("amazon_otp_detection_issue")
                    raise Exception("OTP page detected but input field not found")
                logger.info("OTP not required")
                return

            logger.info("OTP verification required")

            if not settings.amazon_otp_secret:
                raise Exception("OTP required but AMAZON_OTP_SECRET not configured!")

            # Generate OTP code
            totp = pyotp.TOTP(settings.amazon_otp_secret.replace(" ", ""))
            otp_code = totp.now()
            logger.info(f"Generated OTP code: {otp_code}")

            # Enter OTP
            otp_input.fill(otp_code)

            # Check "Keep me signed in" if available (might be on OTP page)
            try:
                remember_signin = self.page.locator("#rememberMe")
                if not remember_signin.is_checked(timeout=2000):
                    remember_signin.check()
                    logger.info("Checked 'Keep me signed in'")
            except Exception:
                pass  # Not found, that's okay

            # Check "Don't require OTP on this device" if available
            try:
                remember_device = self.page.locator("#auth-mfa-remember-device")
                if not remember_device.is_checked(timeout=2000):
                    remember_device.check()
                    logger.info("Checked 'Don't require OTP on this device'")
            except Exception:
                pass  # Not found, that's okay

            # Submit OTP
            submit_button = self.page.locator("#auth-signin-button")
            submit_button.click()
            logger.info("Submitted OTP code")

            time.sleep(2)

        except Exception as e:
            logger.error(f"OTP handling failed: {e}")
            self._save_screenshot("amazon_otp_error")
            raise

    def _handle_additional_prompts(self) -> None:
        """Handle additional prompts like 'Add phone number', 'Skip for now', etc."""
        try:
            # Common skip buttons
            skip_selectors = [
                "a:has-text('Skip')",
                "a:has-text('Not now')",
                "a:has-text('Skip for now')",
                "input[value='Skip']",
                "#ap-account-fixup-phone-skip-link",
            ]

            for selector in skip_selectors:
                try:
                    skip_button = self.page.locator(selector).first
                    if skip_button.is_visible(timeout=2000):
                        skip_button.click()
                        logger.info(f"Clicked skip button: {selector}")
                        time.sleep(1)
                        break
                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"No additional prompts to handle: {e}")

    def _save_screenshot(self, name: str) -> None:
        """Save screenshot for debugging.

        Args:
            name: Screenshot name
        """
        try:
            screenshot_path = f"logs/{name}_{int(time.time())}.png"
            self.page.screenshot(path=screenshot_path)
            logger.info(f"Screenshot saved: {screenshot_path}")
        except Exception as e:
            logger.error(f"Failed to save screenshot: {e}")

    def close(self) -> None:
        """Close browser context and page."""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            logger.info("Closed Amazon session")
        except Exception as e:
            logger.error(f"Error closing Amazon session: {e}")
