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

        Navigates to /orders and checks for "Purchase history" heading,
        which only appears when truly logged in.

        Returns:
            True if session is valid
        """
        try:
            # Go to Walmart orders page - only shows content when logged in
            self.page.goto(f"{settings.walmart_base_url}/orders", wait_until="domcontentloaded")
            time.sleep(3)

            # Check if we're redirected to login page
            current_url = self.page.url
            if "login" in current_url or "signin" in current_url:
                logger.info("Not logged in (redirected to login page)")
                return False

            # Check for "Purchase history" heading - definitive proof of login
            try:
                purchase_history = self.page.locator(
                    "h1:has-text('Purchase history'), "
                    "h1:has-text('purchase history'), "
                    "[data-automation-id='purchase-history']"
                ).first
                purchase_history.wait_for(state="visible", timeout=5000)
                logger.success("Walmart session is valid (Purchase history found)")
                return True
            except TimeoutError:
                logger.info("Could not find Purchase history heading - not logged in")
                return False

        except Exception as e:
            logger.error(f"Session validation failed: {e}")
            return False

    def _login(self) -> None:
        """Perform Walmart login with email 2FA.

        Login flow:
        1. Navigate to sign-in page
        2. Enter email in the email/phone field
        3. Click Continue (#login-continue-button)
        4. Select Password radio button
        5. Enter password
        6. Check "Keep me signed in" checkbox
        7. Click Sign In (#withpassword-sign-in-button)
        8. Handle 2FA if required
        9. Verify login success

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

            # Step 1: Enter email/phone
            logger.info("Entering email...")
            email_input = self.page.locator(
                "input[name='Phone number or email'], "
                "input[autocomplete='email'], "
                "input[type='email'], "
                "input[type='text'][name*='email' i]"
            ).first
            email_input.wait_for(state="visible", timeout=10000)
            email_input.fill(settings.walmart_email)
            logger.info("Entered email")
            time.sleep(1)

            # Step 2: Click Continue button
            logger.info("Clicking Continue...")
            continue_button = self.page.locator(
                "#login-continue-button, "
                "button:has-text('Continue'), "
                "button[type='submit']"
            ).first
            continue_button.click()
            logger.info("Clicked Continue")
            time.sleep(2)

            # Step 3: Select "Password" sign-in method
            logger.info("Selecting password sign-in method...")
            try:
                password_radio = self.page.locator(
                    "input[name='password'][type='radio'], "
                    "input[type='radio'][value='password'], "
                    "label:has-text('Password') input[type='radio']"
                ).first
                password_radio.wait_for(state="attached", timeout=5000)
                if not password_radio.is_checked():
                    password_radio.click(force=True)
                    logger.info("Selected 'Password' sign-in method")
                    time.sleep(1)
                else:
                    logger.info("Password method already selected")
            except Exception as e:
                logger.warning(f"Could not click password radio button: {e}")

            # Step 4: Enter password
            logger.info("Entering password...")
            password_input = self.page.locator(
                "input[autocomplete='current-password'], "
                "input[name='password'][type='password'], "
                "input[type='password']"
            ).first
            password_input.wait_for(state="visible", timeout=10000)
            password_input.fill(settings.walmart_password)
            logger.info("Entered password")
            time.sleep(0.5)

            # Step 5: Check "Keep me signed in" checkbox
            try:
                keep_signed_in = self.page.locator(
                    "#signin-checkboxes input[type='checkbox'], "
                    "label:has-text('Keep me signed in') input[type='checkbox'], "
                    "input[type='checkbox'][name*='remember'], "
                    "input[type='checkbox'][aria-label*='signed in' i]"
                ).first
                keep_signed_in.wait_for(state="attached", timeout=3000)
                if not keep_signed_in.is_checked():
                    keep_signed_in.check(force=True)
                    logger.success("Checked 'Keep me signed in' checkbox")
                else:
                    logger.info("'Keep me signed in' already checked")
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Could not find or check 'Keep me signed in' checkbox: {e}")

            # Step 6: Click Sign In button
            signin_button = self.page.locator(
                "#withpassword-sign-in-button, "
                "button[data-automation-id='withpassword-sign-in-button'], "
                "button:has-text('Sign in'), "
                "button[type='submit']"
            ).first
            signin_button.click()
            logger.info("Clicked Sign-In button")

            # Wait for page to load
            time.sleep(5)

            # Handle 2FA if required
            self._handle_2fa()

            # Handle "Trust this device" prompt
            self._handle_trust_device()

            # Wait for final navigation
            time.sleep(3)

            # Verify login by checking for orders page or non-login URL
            current_url = self.page.url
            if "login" in current_url or "signin" in current_url or "verify" in current_url:
                logger.warning(f"Still on auth page: {current_url}")
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
        """Handle 2FA verification via email (optional - may not appear).

        Walmart 2FA flow (only if required):
        1. Detect "Verify it's you" page (data-dca-name="quickSecurityCheck")
        2. Select email verification radio (input[name="otpEmail"])
        3. Click "Send code" button
        4. Enter 6-digit code into individual input fields (#input-verificationCode through #input-verificationCode-5)
        5. Click sign in button in #verifyitsyou-otp-form

        If the persistent browser profile is recognized by Walmart, 2FA is skipped entirely.
        """
        try:
            # Only detect 2FA by actual page elements, NOT by URL
            # (URLs may transiently contain "verify" during normal redirects)
            is_2fa_page = False

            # Check for the quickSecurityCheck section or "Verify it's you" heading
            try:
                verify_section = self.page.locator(
                    "[data-dca-name='quickSecurityCheck'], "
                    "h1:has-text('Verify it\\'s you'), "
                    "#verifyitsyou-otp-form"
                ).first
                if verify_section.is_visible(timeout=5000):
                    logger.info("2FA verification page detected")
                    is_2fa_page = True
            except Exception:
                pass

            if not is_2fa_page:
                logger.info("2FA not required (no verification elements found)")
                return

            logger.info("2FA required - handling email verification")

            # Select email verification radio button
            try:
                email_radio = self.page.locator(
                    "input[name='otpEmail'][type='radio'], "
                    "input[name='otpEmail'], "
                    "label:has-text('Email') input[type='radio']"
                ).first
                email_radio.wait_for(state="attached", timeout=5000)
                if not email_radio.is_checked():
                    email_radio.click(force=True)
                    logger.info("Selected email as 2FA method")
                    time.sleep(1)
                else:
                    logger.info("Email 2FA method already selected")
            except Exception as e:
                logger.info(f"Email radio not found or already selected: {e}")

            # Click "Send code" button
            try:
                send_button = self.page.locator(
                    "[data-dca-name='quickSecurityCheck'] button[type='submit'], "
                    "button:has-text('Send code'), "
                    "button:has-text('Send')"
                ).first
                if send_button.is_visible(timeout=3000):
                    send_button.click()
                    logger.info("Clicked 'Send code' button")
                    time.sleep(3)
            except Exception:
                logger.debug("Send button not found or already sent")

            # Wait for verification code input fields
            try:
                first_code_input = self.page.locator(
                    "#input-verificationCode, "
                    "input[id^='input-verificationCode']"
                ).first
                first_code_input.wait_for(state="visible", timeout=10000)
            except TimeoutError:
                logger.error("Could not find verification code input field")
                self._save_screenshot("walmart_2fa_no_input")
                raise

            logger.info("=" * 60)
            logger.info("WALMART 2FA CODE REQUIRED")
            logger.info("=" * 60)
            logger.info("A verification code has been sent to your email.")
            logger.info("Please check your email and enter the code below.")
            logger.info("=" * 60)

            # Prompt user for code
            verification_code = input("Enter the 6-digit 2FA code from your email: ").strip()

            if not verification_code:
                raise Exception("No verification code provided")

            # Enter each digit into individual input fields
            # Fields are: #input-verificationCode, #input-verificationCode-1, ..., #input-verificationCode-5
            for i, digit in enumerate(verification_code[:6]):
                input_id = "#input-verificationCode" if i == 0 else f"#input-verificationCode-{i}"
                try:
                    digit_input = self.page.locator(input_id)
                    digit_input.fill(digit)
                except Exception:
                    # Fallback: try typing into the first field and let auto-advance handle it
                    if i == 0:
                        first_code_input.fill(verification_code)
                        break
            logger.info("Entered verification code")
            time.sleep(1)

            # Submit the code via the form's sign-in button
            submit_button = self.page.locator(
                "#verifyitsyou-otp-form button[type='submit'], "
                "#verifyitsyou-otp-form button:has-text('Sign in'), "
                "button:has-text('Verify'), "
                "button:has-text('Sign in')"
            ).first
            submit_button.click()
            logger.info("Submitted verification code")

            time.sleep(5)

            # Verify we're past 2FA
            current_url = self.page.url
            if "verify" not in current_url.lower():
                logger.success("2FA verification passed!")
            else:
                logger.warning(f"May still be on verification page: {current_url}")
                self._save_screenshot("walmart_2fa_still_verifying")

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
                    viewport = self.page.viewport_size
                    x = viewport['width'] / 2
                    y = viewport['height'] * 0.25
            else:
                viewport = self.page.viewport_size
                x = viewport['width'] / 2
                y = viewport['height'] * 0.25
                logger.info(f"Using coordinate-based click at ({x}, {y})")

            for attempt in range(3):
                logger.info(f"Press & Hold attempt {attempt + 1}/3 at ({x}, {y})")

                self.page.mouse.move(x, y)
                time.sleep(0.5)

                self.page.mouse.down()
                hold_time = 10 + attempt * 2
                logger.info(f"Holding for {hold_time} seconds...")
                time.sleep(hold_time)
                self.page.mouse.up()

                logger.info("Released, waiting for verification...")
                time.sleep(5)

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
