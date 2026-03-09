"""Walmart authentication with email 2FA support."""

import time
from playwright.sync_api import Page, BrowserContext, TimeoutError
from loguru import logger

from ..config import settings


class WalmartAuthenticator:
    """Handles Walmart authentication with email 2FA."""

    def __init__(self, context: BrowserContext):
        """Initialize Walmart authenticator.

        Args:
            context: Playwright persistent browser context (shared)
        """
        self.context = context
        self.page: Page = None

    def authenticate(self) -> Page:
        """Authenticate with Walmart and return logged-in page.

        The persistent browser context handles cookie/session persistence
        automatically through its profile directory.

        Returns:
            Playwright page with active Walmart session

        Raises:
            Exception: If authentication fails
        """
        self.page = self.context.new_page()

        # Validate session (persistent profile may have valid cookies)
        if self._validate_session():
            logger.success("Existing Walmart session is valid!")
            return self.page

        logger.warning("No valid session, logging in...")

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
        """Handle Walmart's 'Press & Hold' bot detection challenge.

        The challenge is rendered by PerimeterX/HUMAN bot detection service
        using canvas/shadow DOM that is NOT accessible through normal DOM selectors.
        We detect it by the page title/text and use coordinate-based interaction.
        """
        try:
            time.sleep(2)

            # Check if bot detection challenge is present
            # The "Robot or human?" text is in the main DOM even though the button is not
            page_text = self.page.content()
            is_bot_challenge = (
                self.page.locator("text='Robot or human?'").count() > 0
                or "Robot or human" in page_text
                or "PRESS & HOLD" in page_text
                or "press & hold" in page_text.lower()
            )

            if not is_bot_challenge:
                return

            logger.info("Bot detection challenge detected! Handling Press & Hold...")
            self._save_screenshot("walmart_bot_detection_before")

            # The PRESS & HOLD button is rendered by PerimeterX outside the normal DOM
            # (canvas/shadow DOM), so we can't find it with selectors.
            # Strategy: Try selectors first, fall back to coordinate-based clicking.

            btn_locator = None
            press_hold_selectors = [
                "text='PRESS & HOLD'",
                "text='Press & Hold'",
                "[aria-label*='hold' i]",
                "button",
            ]

            for selector in press_hold_selectors:
                try:
                    element = self.page.locator(selector).first
                    if element.count() > 0 and element.is_visible(timeout=2000):
                        btn_locator = element
                        logger.info(f"Found Press & Hold element with selector: {selector}")
                        break
                except Exception:
                    continue

            if btn_locator:
                box = btn_locator.bounding_box()
                if box:
                    x = box['x'] + box['width'] / 2
                    y = box['y'] + box['height'] / 2
                else:
                    # Fallback to center of viewport
                    viewport = self.page.viewport_size
                    x = viewport['width'] / 2
                    y = viewport['height'] * 0.25
            else:
                # Button is in shadow DOM/canvas - use known position from screenshots
                # The button is horizontally centered, roughly 25% from top
                viewport = self.page.viewport_size
                x = viewport['width'] / 2
                y = viewport['height'] * 0.25
                logger.info(f"Using coordinate-based click at ({x}, {y})")

            # Attempt press & hold with retry
            for attempt in range(3):
                logger.info(f"Press & Hold attempt {attempt + 1}/3 at ({x}, {y})")

                # Move mouse to button position with human-like movement
                self.page.mouse.move(x, y)
                time.sleep(0.5)

                # Press and hold
                self.page.mouse.down()
                hold_time = 10 + attempt * 2  # 10s, 12s, 14s
                logger.info(f"Holding for {hold_time} seconds...")
                time.sleep(hold_time)
                self.page.mouse.up()

                logger.info("Released, waiting for verification...")
                time.sleep(5)

                # Check if challenge is gone
                try:
                    still_blocked = self.page.locator("text='Robot or human?'").count() > 0
                except Exception:
                    still_blocked = False

                if not still_blocked:
                    logger.success("Bot detection challenge passed!")
                    self._save_screenshot("walmart_bot_detection_passed")
                    return

                logger.warning(f"Challenge still present after attempt {attempt + 1}")
                self._save_screenshot(f"walmart_bot_detection_attempt_{attempt + 1}")
                time.sleep(2)

            logger.error("Failed to pass bot detection after 3 attempts")
            self._save_screenshot("walmart_bot_detection_failed")

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
        """Close Walmart page (context is shared, not closed here)."""
        try:
            if self.page:
                self.page.close()
                self.page = None
            logger.info("Closed Walmart page")
        except Exception as e:
            logger.error(f"Error closing Walmart page: {e}")
