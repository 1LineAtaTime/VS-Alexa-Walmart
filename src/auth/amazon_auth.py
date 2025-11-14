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

            # Check for CAPTCHA/puzzle before clicking Sign-In
            self._check_for_captcha()

            # IMPORTANT: Add small delay before submission to appear more human-like
            time.sleep(1)

            # Click Sign-In and wait for navigation
            # Use multiple strategies to ensure click works
            signin_button = self.page.locator("#signInSubmit")

            # Wait for button to be truly clickable
            signin_button.wait_for(state="visible", timeout=5000)

            # Ensure password field is filled (sometimes it gets cleared)
            password_value = self.page.locator("#ap_password").input_value()
            if not password_value:
                logger.warning("Password field empty before submit, refilling")
                self.page.locator("#ap_password").fill(settings.amazon_password)
                time.sleep(0.5)

            # Try multiple submission methods (most human-like first)
            logger.info("Attempting to submit Sign-In form...")

            # Method 1: Press Enter in password field (most human-like)
            try:
                logger.info("Method 1: Pressing Enter in password field...")
                with self.page.expect_navigation(timeout=20000, wait_until="domcontentloaded"):
                    self.page.locator("#ap_password").press("Enter")
                logger.info("Form submitted with Enter key and page navigated")
            except Exception as e:
                logger.warning(f"Enter key submission failed: {e}")

                # Method 2: Standard button click
                try:
                    logger.info("Method 2: Clicking Sign-In button...")
                    with self.page.expect_navigation(timeout=15000, wait_until="domcontentloaded"):
                        signin_button.click(timeout=5000)
                    logger.info("Sign-In clicked and page navigated")
                except Exception as e2:
                    logger.warning(f"Standard click failed: {e2}")

                    # Method 3: Submit the form directly (bypasses button)
                    try:
                        logger.info("Method 3: Submitting form directly with JavaScript...")
                        self.page.evaluate("document.querySelector('form[name=\"signIn\"]').submit()")
                        logger.info("Form submitted with JavaScript")
                        time.sleep(4)  # Wait for navigation
                    except Exception as e3:
                        logger.warning(f"Form submit failed: {e3}, trying button click with force")

                        # Method 4: Force click as last resort
                        signin_button.click(force=True, timeout=5000)
                        logger.info("Sign-In clicked with force")
                        time.sleep(3)

            # Wait for navigation after clicking Sign-In
            # Amazon can either:
            # 1. Redirect to OTP page
            # 2. Redirect to success page
            # 3. Stay on signin page (but you're actually logged in)
            logger.info("Waiting for page transition after Sign-In...")

            # First, wait a moment for any immediate navigation
            time.sleep(2)

            # Try to detect navigation by checking for URL change or page state change
            initial_url = self.page.url
            try:
                # Wait for either URL change OR disappearance of password field
                self.page.wait_for_function(
                    """() => {
                        const url = window.location.href;
                        const passwordField = document.querySelector('#ap_password');
                        return url !== arguments[0] || (passwordField && !passwordField.offsetParent);
                    }""",
                    arg=initial_url,
                    timeout=10000
                )
                logger.info("Page transitioned after sign-in")
            except Exception as e:
                logger.debug(f"No clear page transition detected: {e}")

            # Wait for any ongoing navigation to complete
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass

            # Additional wait for dynamic content
            time.sleep(1)

            # Debug: Log current URL to see where we are
            current_url = self.page.url
            logger.info(f"Current URL after sign-in: {current_url}")

            # Check for error messages on the page (multiple possible locations)
            error_found = False
            try:
                # Try multiple error message selectors
                error_selectors = [
                    "#auth-error-message-box",
                    ".a-alert-error",
                    "[data-a-alert-type='error']",
                    ".auth-error-message",
                    "#auth-warning-message-box",
                    ".a-alert-warning"
                ]

                for error_selector in error_selectors:
                    try:
                        error_box = self.page.locator(error_selector).first
                        if error_box.is_visible(timeout=1000):
                            error_text = error_box.inner_text()
                            logger.error(f"Amazon error/warning message ({error_selector}): {error_text}")
                            self._save_screenshot("amazon_login_error_message")
                            error_found = True

                            # Only raise if it's a critical error (not just a warning)
                            if "error" in error_selector.lower():
                                raise Exception(f"Amazon login error: {error_text}")
                    except TimeoutError:
                        continue

            except Exception as e:
                if "Amazon login error:" in str(e):
                    raise
                # No critical error found

            # If we're still on the sign-in page, investigate why
            if "/ap/signin" in current_url and "shopping" not in current_url:
                logger.warning("Still on sign-in page after clicking Sign-In")

                # Check what's visible on the page
                self._debug_page_state()

                self._save_screenshot("amazon_stuck_on_signin")
                logger.warning("Screenshot saved - check logs/ directory")

                # Check if button is still there (might indicate validation error)
                try:
                    if self.page.locator("#signInSubmit").is_visible(timeout=2000):
                        logger.warning("Sign-In button still visible - click may not have registered")

                        # Check if password field has validation errors
                        password_field = self.page.locator("#ap_password").first
                        if password_field.is_visible(timeout=1000):
                            # Check for validation attributes
                            aria_invalid = password_field.get_attribute("aria-invalid")
                            if aria_invalid == "true":
                                logger.error("Password field marked as invalid")
                except Exception:
                    pass

            # Handle OTP if required
            self._handle_otp()

            # Handle "Not now" for additional security prompts
            self._handle_additional_prompts()

            # Verify we're logged in by navigating to shopping list
            logger.info("Verifying login by accessing shopping list...")
            self.page.goto("https://www.amazon.com/gp/alexa-shopping-list", wait_until="domcontentloaded")
            time.sleep(3)

            # Check if we're still on sign-in page (login failed)
            current_check_url = self.page.url
            logger.info(f"Current URL after shopping list navigation: {current_check_url}")

            if "/ap/signin" in current_check_url or "/ap/cvf" in current_check_url:
                logger.error("Redirected back to sign-in page - authentication failed!")
                self._save_screenshot("amazon_auth_failed_redirect")
                raise Exception(
                    "Authentication failed - redirected back to sign-in. "
                    "This usually indicates bot detection or incorrect credentials. "
                    "The sign-in button click may not be working."
                )

            # Double-check by looking for password field
            try:
                password_field = self.page.locator("#ap_password, input[type='password'][name='password']").first
                if password_field.is_visible(timeout=2000):
                    logger.error("Password field still visible - authentication failed")
                    self._save_screenshot("amazon_auth_failed_password_visible")
                    raise Exception("Login failed - still on sign-in page after authentication")
            except TimeoutError:
                pass  # Good - no password field means we're logged in

            # Verify we can actually see shopping list content (not empty due to failed auth)
            try:
                # Look for shopping list container
                list_container = self.page.locator("#shopping-list-items, [data-component='shopping-list'], .shopping-list-container").first
                if list_container.is_visible(timeout=5000):
                    logger.info("Shopping list container found - authentication appears successful")
                else:
                    logger.warning("Shopping list container not found - may indicate authentication issue")
            except Exception as e:
                logger.warning(f"Could not verify shopping list container: {e}")

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

            # First check URL for OTP indicators
            on_otp_page = any(keyword in current_url for keyword in ['mfa', 'otp', 'verify', 'two-step'])

            if on_otp_page:
                logger.info("OTP page detected by URL")
                # Give it extra time to load
                time.sleep(2)

            # Check if OTP is required - try multiple selectors
            otp_input = None
            otp_selectors = [
                "#auth-mfa-otpcode",
                "input[name='otpCode']",
                "input[aria-label*='OTP']",
                "input[aria-label*='code']",
                "input[id*='otp']",
                "input[placeholder*='code' i]"
            ]

            # Try each selector individually for better debugging
            for selector in otp_selectors:
                try:
                    otp_input = self.page.wait_for_selector(selector, timeout=2000, state="visible")
                    if otp_input:
                        logger.info(f"OTP input found with selector: {selector}")
                        break
                except TimeoutError:
                    continue

            # If no input found but URL suggests OTP page
            if not otp_input and on_otp_page:
                logger.warning("OTP page detected by URL but input field not found")
                self._save_screenshot("amazon_otp_detection_issue")

                # Log what's actually on the page
                page_text = self.page.text_content("body")
                if "one-time" in page_text.lower() or "verification" in page_text.lower():
                    logger.error("Page mentions OTP/verification but can't find input")

                raise Exception("OTP page detected but input field not found - selectors may need updating")

            if not otp_input:
                logger.info("OTP not required (no OTP input field found)")
                return

            logger.info("OTP verification required")

            if not settings.amazon_otp_secret:
                raise Exception("OTP required but AMAZON_OTP_SECRET not configured!")

            # Generate OTP code
            # Add small delay to ensure time sync (OTP codes are time-sensitive)
            time.sleep(3)
            totp = pyotp.TOTP(settings.amazon_otp_secret.replace(" ", ""))
            otp_code = totp.now()
            logger.info(f"Generated OTP code: {otp_code}")
            logger.info(f"OTP code length: {len(otp_code)}, expected: 6")

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

    def _debug_page_state(self) -> None:
        """Debug helper to log what's visible on the page."""
        try:
            logger.debug("=== Page State Debug ===")

            # Check what form fields are visible
            visible_inputs = self.page.locator("input[type='email'], input[type='password'], input[type='text']").all()
            logger.debug(f"Visible input fields: {len(visible_inputs)}")

            for inp in visible_inputs[:5]:  # Log first 5
                try:
                    input_id = inp.get_attribute("id") or "no-id"
                    input_name = inp.get_attribute("name") or "no-name"
                    input_type = inp.get_attribute("type") or "unknown"
                    logger.debug(f"  - Input: id={input_id}, name={input_name}, type={input_type}")
                except Exception:
                    pass

            # Check for any buttons
            buttons = self.page.locator("button, input[type='submit']").all()
            logger.debug(f"Visible buttons: {len(buttons)}")

            # Check page title
            title = self.page.title()
            logger.debug(f"Page title: {title}")

            logger.debug("=== End Page State ===")

        except Exception as e:
            logger.debug(f"Debug page state failed: {e}")

    def _check_for_captcha(self) -> None:
        """Check for CAPTCHA or puzzle challenges that block sign-in.

        Raises:
            Exception: If CAPTCHA detected that requires manual intervention
        """
        try:
            # Check for common Amazon CAPTCHA/puzzle selectors
            captcha_selectors = [
                "img[src*='captcha']",
                "img[src*='puzzle']",
                "#auth-captcha-image",
                "form[action*='validateCaptcha']",
                "[aria-label*='CAPTCHA']",
                "[aria-label*='puzzle']"
            ]

            for selector in captcha_selectors:
                try:
                    captcha_element = self.page.locator(selector).first
                    if captcha_element.is_visible(timeout=1000):
                        logger.error(f"CAPTCHA/Puzzle detected: {selector}")
                        self._save_screenshot("amazon_captcha_detected")
                        raise Exception(
                            "CAPTCHA/Puzzle challenge detected. "
                            "This requires manual intervention. "
                            "Try running with --headed flag and solving the CAPTCHA manually, "
                            "then the session will be saved."
                        )
                except TimeoutError:
                    continue

            logger.debug("No CAPTCHA detected")

        except Exception as e:
            if "CAPTCHA" in str(e):
                raise
            # Other errors can be ignored
            logger.debug(f"CAPTCHA check completed: {e}")

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
