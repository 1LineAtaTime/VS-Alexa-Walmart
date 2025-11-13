"""Walmart authentication with email 2FA support."""

import time
from playwright.sync_api import Page, Browser, BrowserContext, TimeoutError
from loguru import logger

from ..config import settings
from .session_manager import SessionManager


class WalmartAuthenticator:
    """Handles Walmart authentication with email 2FA."""

    def __init__(self, browser: Browser):
        """Initialize Walmart authenticator.

        Args:
            browser: Playwright browser instance
        """
        self.browser = browser
        self.context: BrowserContext = None
        self.page: Page = None
        self.session_manager = SessionManager(settings.walmart_cookies_file)

    def authenticate(self) -> Page:
        """Authenticate with Walmart and return logged-in page.

        Returns:
            Playwright page with active Walmart session

        Raises:
            Exception: If authentication fails
        """
        # Create browser context
        self.context = self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
        )
        self.page = self.context.new_page()

        # Hide webdriver flag
        self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        # Try to load existing cookies
        if self.session_manager.cookies_exist():
            logger.info("Found existing Walmart cookies, attempting to use them")
            self.session_manager.load_cookies(self.context)

            # Validate session
            if self._validate_session():
                logger.success("Existing Walmart session is valid!")
                return self.page

            logger.warning("Existing session invalid, logging in again")
            self.session_manager.clear_cookies()

        # Perform fresh login
        self._login()
        return self.page


    def _validate_session(self) -> bool:
        """Validate that current session is active.

        Returns:
            True if session is valid
        """
        try:
            # Go to Walmart account page
            self.page.goto(f"{settings.walmart_base_url}/account", wait_until="domcontentloaded")
            time.sleep(2)

            # Check if we're redirected to login page
            current_url = self.page.url
            if "login" in current_url or "signin" in current_url:
                logger.info("Not logged in (redirected to login page)")
                return False

            # Look for account indicators
            try:
                # Check for account/profile elements
                account_element = self.page.wait_for_selector(
                    "[data-automation-id='account-flyout'], .account-link, [aria-label*='Account']",
                    timeout=5000
                )
                logger.success("Walmart session is valid")
                return True
            except TimeoutError:
                logger.info("Could not find account elements")
                return False

        except Exception as e:
            logger.error(f"Session validation failed: {e}")
            return False

    def _login(self) -> None:
        """Perform Walmart login with email 2FA.

        Raises:
            Exception: If login fails
        """
        logger.info("Starting Walmart login process")

        try:
            # Navigate to sign-in page
            self.page.goto(settings.walmart_signin_url, wait_until="domcontentloaded")
            logger.info("Navigated to Walmart sign-in page")
            time.sleep(2)

            # Handle bot detection "Press & Hold" challenge
            self._handle_bot_detection()

            # Enter email/phone (Walmart uses a combined field)
            logger.info("Entering email...")
            # Wait for the visible input field (not the hidden autocomplete field)
            email_input = self.page.locator(
                "input[type='text']:not([aria-hidden='true']), "
                "input[type='email']:not([aria-hidden='true']), "
                "input[type='tel']:not([aria-hidden='true'])"
            ).first
            email_input.wait_for(state="visible", timeout=10000)
            email_input.fill(settings.walmart_email)
            time.sleep(1)

            # Click Continue button
            logger.info("Clicking Continue...")
            continue_button = self.page.locator(
                "button:has-text('Continue'), "
                "button[type='submit']"
            ).first
            continue_button.click()
            logger.info("Clicked Continue")
            time.sleep(2)

            # Select "Password" sign-in method (click the radio button)
            logger.info("Selecting password sign-in method...")
            try:
                password_radio = self.page.locator(
                    "input[type='radio'][value='password'], "
                    "label:has-text('Password') input[type='radio']"
                ).first
                if not password_radio.is_checked():
                    password_radio.click()
                    logger.info("Selected 'Password' sign-in method")
                    time.sleep(1)
            except Exception as e:
                logger.warning(f"Could not click password radio button: {e}")

            # Now enter password
            logger.info("Entering password...")
            password_input = self.page.locator(
                "input[type='password']:not([aria-hidden='true'])"
            ).first
            password_input.wait_for(state="visible", timeout=10000)
            password_input.fill(settings.walmart_password)
            time.sleep(0.5)

            # Check "Remember me" checkbox if available
            try:
                # Try multiple selectors for the Remember me checkbox
                remember_checkbox = self.page.locator(
                    "input[type='checkbox'][name*='remember'], "
                    "input[type='checkbox']#remember, "
                    "label:has-text('Remember me') input, "
                    "input[type='checkbox'][id*='remember'], "
                    "input[type='checkbox'][aria-label*='remember' i]"
                ).first

                # Wait for checkbox to be visible
                remember_checkbox.wait_for(state="visible", timeout=3000)

                # Always check it (don't check if it's already checked, just check it)
                remember_checkbox.check(force=True)
                logger.success("Checked 'Remember me' checkbox")
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Could not find or check 'Remember me' checkbox: {e}")

            # Click Sign In button
            signin_button = self.page.locator(
                "button[type='submit'], "
                "button:has-text('Sign In'), "
                "button:has-text('Sign in')"
            ).first
            signin_button.click()
            logger.info("Clicked Sign-In button")

            # Wait for page to load
            time.sleep(5)

            # Handle 2FA if required (check after waiting for page load)
            self._handle_2fa()

            # Handle "Trust this device" prompt
            self._handle_trust_device()

            # Wait a bit more for final navigation
            time.sleep(3)

            # Check if we're logged in (don't strict wait for URL, just check current state)
            current_url = self.page.url
            if "login" in current_url or "signin" in current_url or "verify" in current_url:
                logger.warning(f"Still on auth page: {current_url}")
                # Give it more time
                time.sleep(5)

            # Save cookies for future use
            self.session_manager.save_cookies(self.context)

            logger.success("Walmart login successful!")

        except TimeoutError as e:
            logger.error(f"Timeout during Walmart login: {e}")
            self._save_screenshot("walmart_login_timeout")
            raise Exception(f"Walmart login timeout: {e}")
        except Exception as e:
            logger.error(f"Walmart login failed: {e}")
            self._save_screenshot("walmart_login_error")
            raise Exception(f"Walmart login failed: {e}")

    def _handle_2fa(self) -> None:
        """Handle 2FA verification via email.

        This method will:
        1. Detect if 2FA is required
        2. Select email as verification method (or confirm it's selected)
        3. Send code
        4. Wait for user to enter the code
        """
        try:
            current_url = self.page.url

            # Look for 2FA indicators - check for "Verify" or verification code elements
            is_2fa_page = False

            # Check URL
            if "two-step" in current_url or "verify" in current_url.lower() or "mfa" in current_url:
                logger.info("2FA page detected from URL")
                is_2fa_page = True

            # Check for verification text on page
            try:
                verify_text = self.page.locator("text='Verify it\\'s you'").first
                if verify_text.is_visible(timeout=2000):
                    logger.info("2FA verification page detected")
                    is_2fa_page = True
            except Exception:
                pass

            if not is_2fa_page:
                logger.info("2FA not required")
                return

            # Try to select email as verification method
            try:
                email_option = self.page.locator(
                    "button:has-text('Email'), "
                    "label:has-text('Email'), "
                    "input[value='email']"
                ).first
                if email_option.is_visible(timeout=3000):
                    email_option.click()
                    logger.info("Selected email as 2FA method")
                    time.sleep(2)
            except Exception:
                logger.info("Email option not found or already selected")

            # Try to click "Send code" button if present
            try:
                send_button = self.page.locator(
                    "button:has-text('Send code'), "
                    "button:has-text('Send'), "
                    "button[type='submit']"
                ).first
                if send_button.is_visible(timeout=3000):
                    send_button.click()
                    logger.info("Clicked 'Send code' button")
                    time.sleep(2)
            except Exception:
                logger.debug("Send button not found")

            # Wait for code input fields (Walmart uses 6 individual digit inputs)
            try:
                # Look for the first digit input box
                code_input = self.page.wait_for_selector(
                    "input[type='text'], input[type='tel'], input",
                    timeout=8000
                )
            except TimeoutError:
                logger.error("Could not find verification code input field")
                raise

            logger.info("="*60)
            logger.info("WALMART 2FA CODE REQUIRED")
            logger.info("="*60)
            logger.info("A verification code has been sent to your email.")
            logger.info("Please check your email and enter the code below.")
            logger.info("="*60)

            # Prompt user for code
            verification_code = input("Enter the 6-digit 2FA code from your email: ").strip()

            if not verification_code:
                raise Exception("No verification code provided")

            # Walmart has 6 individual input boxes - we can type into the first one
            # and the digits will auto-advance to the next boxes
            code_input.fill(verification_code)
            logger.info("Entered verification code")
            time.sleep(1)

            # Submit the code
            submit_button = self.page.locator(
                "button[type='submit'], "
                "button:has-text('Verify'), "
                "button:has-text('Submit'), "
                "button:has-text('Continue')"
            ).first
            submit_button.click()
            logger.info("Submitted verification code")

            time.sleep(3)

        except Exception as e:
            logger.error(f"2FA handling failed: {e}")
            self._save_screenshot("walmart_2fa_error")
            raise

    def _handle_bot_detection(self) -> None:
        """Handle Walmart's 'Press & Hold' bot detection challenge."""
        try:
            time.sleep(2)

            # Check if bot detection challenge is present
            if self.page.locator("text='Robot or human?'").count() > 0:
                logger.info("Bot detection challenge detected! Handling Press & Hold...")

                # Find all buttons on the page and select the first visible one
                all_buttons = self.page.locator("button").all()
                logger.info(f"Found {len(all_buttons)} buttons on page")

                btn_locator = None
                for btn in all_buttons:
                    try:
                        if btn.is_visible(timeout=1000):
                            btn_locator = btn
                            logger.info("Found visible Press & Hold button")
                            break
                    except Exception:
                        continue

                if btn_locator:
                    box = btn_locator.bounding_box()
                    if box:
                        x = box['x'] + box['width'] / 2
                        y = box['y'] + box['height'] / 2

                        # Move mouse to button
                        self.page.mouse.move(x, y)

                        # Press and hold for 5 seconds
                        self.page.mouse.down()
                        logger.info("Holding button for 5 seconds...")
                        time.sleep(5)
                        self.page.mouse.up()

                        logger.success("Released button, waiting for verification")
                        time.sleep(5)

                        logger.success("Bot detection challenge passed")
                else:
                    logger.error("Could not find Press & Hold button!")
                    self._save_screenshot("walmart_no_press_hold_button")
        except Exception as e:
            logger.debug(f"No bot detection to handle or error: {e}")

    def _handle_trust_device(self) -> None:
        """Handle 'Trust this device' prompt to avoid future 2FA requests."""
        try:
            # Look for trust device checkbox
            trust_checkbox = self.page.locator(
                "input[type='checkbox'][name*='trust'], "
                "input[type='checkbox'][name*='remember'], "
                "label:has-text('trust this device') input, "
                "label:has-text('remember this device') input, "
                "label:has-text('Don\\'t ask again') input"
            ).first

            if trust_checkbox.is_visible(timeout=3000):
                if not trust_checkbox.is_checked():
                    trust_checkbox.check()
                    logger.info("Checked 'Trust this device'")

                # Click continue/submit button
                continue_button = self.page.locator(
                    "button:has-text('Continue'), "
                    "button:has-text('Done'), "
                    "button[type='submit']"
                ).first
                if continue_button.is_visible(timeout=2000):
                    continue_button.click()
                    logger.info("Clicked Continue")
                    time.sleep(2)
        except Exception as e:
            logger.debug(f"No trust device prompt: {e}")

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
            logger.info("Closed Walmart session")
        except Exception as e:
            logger.error(f"Error closing Walmart session: {e}")
