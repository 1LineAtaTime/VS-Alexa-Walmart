"""Walmart cart management using Playwright."""

import time
from typing import Optional
from playwright.sync_api import Page, TimeoutError
from loguru import logger

from ..config import settings


class WalmartCartManager:
    """Manages Walmart shopping cart operations."""

    def __init__(self, page: Page):
        """Initialize cart manager.

        Args:
            page: Authenticated Playwright page
        """
        self.page = page

    def add_to_cart(self, item_id: str, quantity: int = 1, product_element=None) -> bool:
        """Add item to Walmart cart directly from search results.

        Args:
            item_id: Walmart item/product ID (for logging)
            quantity: Quantity to add
            product_element: Optional product card element from search results

        Returns:
            True if item was added successfully

        Raises:
            Exception: If adding to cart fails
        """
        logger.info(f"Adding item {item_id} to cart (quantity: {quantity})")

        try:
            # If product_element is provided, click Add button directly from search results
            if product_element:
                logger.info("Checking if item is already in cart or needs to be added...")

                # Scroll the product card into view first
                try:
                    logger.info("Scrolling product card into view...")
                    product_element.scroll_into_view_if_needed(timeout=5000)
                    time.sleep(1)  # Give it a moment after scrolling
                    logger.info("Product card scrolled into view")
                except Exception as e:
                    logger.warning(f"Could not scroll product into view: {e}")

                # First, check if item is already in cart (quantity stepper exists)
                quantity_stepper = product_element.locator("div[data-testid='quantity-stepper']").first
                if quantity_stepper.count() > 0:
                    logger.info("Item is already in cart! Checking current quantity...")
                    try:
                        quantity_label = quantity_stepper.locator("span[data-testid='quantity-label']").first
                        current_qty_text = quantity_label.inner_text(timeout=2000).strip()
                        current_qty = int(current_qty_text)
                        logger.success(f"Item already in cart with quantity: {current_qty}")

                        # If desired quantity is different, update it
                        if current_qty != quantity:
                            logger.info(f"Updating quantity from {current_qty} to {quantity}...")

                            # Determine if we need to increase or decrease
                            if quantity > current_qty:
                                # Click + button (increase) multiple times
                                increase_button = quantity_stepper.locator("button[aria-label*='Increase quantity']").first
                                clicks_needed = quantity - current_qty
                                for i in range(clicks_needed):
                                    increase_button.click()
                                    logger.info(f"Increased quantity ({i+1}/{clicks_needed})")
                                    time.sleep(0.5)
                            elif quantity < current_qty:
                                # Click - button (decrease) multiple times
                                decrease_button = quantity_stepper.locator("button[aria-label*='Decrease quantity']").first
                                clicks_needed = current_qty - quantity
                                for i in range(clicks_needed):
                                    decrease_button.click()
                                    logger.info(f"Decreased quantity ({i+1}/{clicks_needed})")
                                    time.sleep(0.5)

                            logger.success(f"Updated quantity to {quantity}")
                        else:
                            logger.info(f"Quantity already correct ({quantity}), no update needed")

                        return True
                    except Exception as e:
                        logger.warning(f"Could not read/update quantity stepper: {e}")
                        # Continue to try adding normally

                # Item not in cart yet - look for Add button
                logger.info("Item not in cart yet. Looking for Add button...")
                add_button = product_element.locator("button[data-automation-id='add-to-cart']").first

                # Wait for button to be visible with longer timeout
                try:
                    logger.info("Waiting for Add button to be visible (up to 10 seconds)...")
                    add_button.wait_for(state="visible", timeout=10000)
                    logger.info("Add button is now visible")
                except Exception as e:
                    logger.error(f"Add button not visible after 10 seconds: {e}")
                    self._save_screenshot("add_button_not_visible")
                    return False

                # Additionally wait for button to be enabled (not disabled)
                try:
                    logger.info("Checking if Add button is enabled...")
                    is_disabled = add_button.is_disabled(timeout=2000)
                    if is_disabled:
                        logger.error("Add button is disabled")
                        self._save_screenshot("add_button_disabled")
                        return False
                    logger.info("Add button is enabled and ready to click")
                except Exception as e:
                    logger.warning(f"Could not check if button is enabled: {e}, proceeding anyway")

                # Scroll the button itself into view as well
                try:
                    logger.info("Scrolling Add button into center of viewport...")
                    add_button.scroll_into_view_if_needed(timeout=3000)
                    time.sleep(0.5)
                    logger.info("Add button scrolled into view")
                except Exception as e:
                    logger.warning(f"Could not scroll button into view: {e}")

                # Get the button text before clicking (should be "Add")
                try:
                    button_text_before = add_button.inner_text(timeout=1000)
                    logger.info(f"Button text before click: '{button_text_before}'")
                except:
                    button_text_before = "Unknown"

                # Click the Add button
                logger.info("Clicking Add button...")
                add_button.click()
                logger.info("Clicked Add button on search results")

                # Wait for cart to update and verify success
                time.sleep(2)

                # Verify addition by checking for quantity-in-cart button
                try:
                    # Check if a quantity button appeared (indicates item is in cart)
                    quantity_button = product_element.locator('button[data-testid="quantity-in-cart"]').first
                    if quantity_button.is_visible(timeout=2000):
                        quantity_text = quantity_button.inner_text(timeout=1000).strip()
                        logger.success(f"Item {item_id} added to cart - quantity button shows: '{quantity_text}'")
                        return True
                except Exception:
                    pass

                # Fallback: Check if button text changed
                try:
                    button_text_after = add_button.inner_text(timeout=1000)
                    logger.info(f"Button text after click: '{button_text_after}'")

                    if button_text_after != button_text_before and button_text_after.strip() in ["1", "2", "3", "4", "5"]:
                        logger.success(f"Item {item_id} added to cart (button changed to '{button_text_after}')")
                        return True
                    elif button_text_after != button_text_before:
                        logger.success(f"Item {item_id} added to cart (button changed from '{button_text_before}' to '{button_text_after}')")
                        return True
                except Exception:
                    pass

                # Assume success if we got this far without errors
                logger.info("Could not verify button change, but click succeeded - assuming added to cart")
                return True

            # Fallback: Navigate to product page (old behavior)
            else:
                logger.warning("No product element provided, falling back to product page navigation")
                product_url = f"{settings.walmart_base_url}/ip/{item_id}"
                self.page.goto(product_url, wait_until="domcontentloaded")
                logger.info(f"Navigated to product page: {product_url}")
                time.sleep(3)

                # Find and click "Add to cart" button
                add_to_cart_button = None
                add_button_selectors = [
                    "button[data-automation-id='add-to-cart']",
                    "button:has-text('Add to cart')",
                    "button[aria-label*='Add to cart']",
                    "button:has-text('Add')",
                    "[data-testid='add-to-cart-button']",
                    ".add-to-cart-button"
                ]

                for selector in add_button_selectors:
                    try:
                        button = self.page.locator(selector).first
                        if button.is_visible(timeout=3000):
                            add_to_cart_button = button
                            logger.info(f"Found Add button with selector: {selector}")
                            break
                    except Exception:
                        continue

                if not add_to_cart_button:
                    logger.error("Could not find 'Add to cart' button")
                    self._save_screenshot("walmart_no_add_button")
                    return False

                # Click add to cart
                add_to_cart_button.click()
                logger.info("Clicked 'Add to cart' button")
                time.sleep(3)

                # Handle any popups or modals
                self._handle_post_add_modals()

                logger.success(f"Assuming item {item_id} was added to cart")
                return True

        except Exception as e:
            logger.error(f"Failed to add item to cart: {e}")
            self._save_screenshot("walmart_add_to_cart_error")
            raise Exception(f"Add to cart failed: {e}")

    def _check_product_available(self) -> bool:
        """Check if product is available for purchase.

        Returns:
            True if product is available
        """
        try:
            # Check for out of stock indicators
            unavailable_selectors = [
                "text='Out of stock'",
                "text='Sold out'",
                "text='Unavailable'",
                "text='Not available'",
                "[data-automation-id='out-of-stock']"
            ]

            for selector in unavailable_selectors:
                try:
                    if self.page.locator(selector).is_visible(timeout=1000):
                        logger.warning(f"Product unavailable: {selector}")
                        return False
                except Exception:
                    continue

            return True

        except Exception:
            return True  # Assume available if we can't determine

    def _set_quantity(self, quantity: int) -> None:
        """Set quantity for the product.

        Args:
            quantity: Desired quantity
        """
        try:
            quantity_selectors = [
                "input[data-automation-id='quantity-input']",
                "input[aria-label*='Quantity']",
                "select[data-automation-id='quantity-select']",
                ".quantity-input"
            ]

            for selector in quantity_selectors:
                try:
                    quantity_input = self.page.locator(selector).first
                    if quantity_input.is_visible(timeout=2000):
                        # Check if it's a select or input
                        tag_name = quantity_input.evaluate("el => el.tagName")

                        if tag_name.lower() == "select":
                            quantity_input.select_option(str(quantity))
                        else:
                            quantity_input.fill(str(quantity))

                        logger.info(f"Set quantity to {quantity}")
                        time.sleep(0.5)
                        return
                except Exception:
                    continue

            logger.warning("Could not find quantity selector")

        except Exception as e:
            logger.warning(f"Failed to set quantity: {e}")

    def _handle_post_add_modals(self) -> None:
        """Handle any modals or popups after adding to cart."""
        try:
            # Look for close/continue shopping buttons
            close_selectors = [
                "button:has-text('Continue shopping')",
                "button:has-text('Close')",
                "button[aria-label='Close']",
                ".modal-close",
                "[data-automation-id='close-modal']"
            ]

            for selector in close_selectors:
                try:
                    button = self.page.locator(selector).first
                    if button.is_visible(timeout=2000):
                        button.click()
                        logger.info(f"Closed modal: {selector}")
                        time.sleep(1)
                        return
                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"No modal to handle: {e}")

    def _verify_item_added(self) -> bool:
        """Verify that item was added to cart.

        Returns:
            True if verification successful
        """
        try:
            # Look for success indicators
            success_selectors = [
                "text='Added to cart'",
                "text='Item added'",
                "[data-automation-id='added-to-cart']",
                ".cart-confirmation"
            ]

            for selector in success_selectors:
                try:
                    if self.page.locator(selector).is_visible(timeout=3000):
                        logger.info(f"Verified item added: {selector}")
                        return True
                except Exception:
                    continue

            # Alternative: Check if cart count increased
            try:
                cart_count = self.page.locator(
                    "[data-automation-id='cart-count'], "
                    ".cart-count, "
                    "[aria-label*='cart'] [data-count]"
                ).first
                if cart_count.is_visible(timeout=2000):
                    count_text = cart_count.inner_text(timeout=1000)
                    if count_text and count_text.strip() != "0":
                        logger.info(f"Cart count: {count_text}")
                        return True
            except Exception:
                pass

            return False

        except Exception:
            return False

    def get_cart_count(self) -> int:
        """Get number of items in cart.

        Returns:
            Number of items in cart
        """
        try:
            self.page.goto(f"{settings.walmart_base_url}/cart", wait_until="domcontentloaded")
            time.sleep(2)

            # Count items in cart
            item_count = self.page.locator(
                "[data-automation-id='cart-item'], "
                ".cart-item, "
                "[data-product-id]"
            ).count()

            logger.info(f"Cart has {item_count} items")
            return item_count

        except Exception as e:
            logger.error(f"Failed to get cart count: {e}")
            return 0

    def clear_cart(self) -> bool:
        """Clear all items from cart.

        Returns:
            True if cart was cleared

        Raises:
            Exception: If clearing fails
        """
        logger.info("Clearing Walmart cart")

        try:
            self.page.goto(f"{settings.walmart_base_url}/cart", wait_until="domcontentloaded")
            time.sleep(2)

            initial_count = self.get_cart_count()
            logger.info(f"Cart has {initial_count} items")

            if initial_count == 0:
                logger.info("Cart is already empty")
                return True

            # Remove items one by one
            cleared = 0
            while cleared < initial_count:
                try:
                    # Find first remove button
                    remove_button = self.page.locator(
                        "button[aria-label*='Remove'], "
                        "button:has-text('Remove'), "
                        "[data-automation-id='remove-item']"
                    ).first

                    if remove_button.is_visible(timeout=3000):
                        remove_button.click()
                        logger.info(f"Removed item {cleared + 1}")
                        cleared += 1
                        time.sleep(1)
                    else:
                        break

                except TimeoutError:
                    break

            final_count = self.get_cart_count()
            logger.success(f"Cleared {cleared} items, {final_count} remaining")

            return final_count == 0

        except Exception as e:
            logger.error(f"Failed to clear cart: {e}")
            raise Exception(f"Cart clearing failed: {e}")

    def _save_screenshot(self, name: str) -> None:
        """Save screenshot for debugging.

        Args:
            name: Screenshot name
        """
        try:
            screenshot_path = f"logs/{name}_{int(time.time())}.png"
            self.page.screenshot(path=screenshot_path, full_page=True)
            logger.info(f"Screenshot saved: {screenshot_path}")
        except Exception as e:
            logger.error(f"Failed to save screenshot: {e}")
