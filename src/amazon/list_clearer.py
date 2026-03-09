"""Amazon shopping list clearer."""

import time
from playwright.sync_api import Page, TimeoutError
from loguru import logger

from ..config import settings


class AmazonListClearer:
    """Clears items from Amazon Alexa shopping list."""

    def __init__(self, page: Page):
        """Initialize list clearer.

        Args:
            page: Authenticated Playwright page
        """
        self.page = page

    def clear_list(self) -> bool:
        """Clear all items from Amazon shopping list.

        Returns:
            True if list was cleared successfully

        Raises:
            Exception: If clearing fails
        """
        logger.info("Clearing Amazon shopping list")

        try:
            # Navigate to shopping list
            self.page.goto(settings.amazon_list_url, wait_until="domcontentloaded")
            time.sleep(3)  # Wait for dynamic content

            # Get initial count by counting Delete buttons
            initial_count = self._get_item_count()
            logger.info(f"Found {initial_count} items to clear")

            if initial_count == 0:
                logger.info("List is already empty")
                return True

            # Clear items one by one
            cleared_count = 0

            while cleared_count < initial_count:
                try:
                    # Always find the first Delete button (they shift after each deletion)
                    delete_buttons = self.page.locator("button:has-text('Delete')").all()

                    if not delete_buttons or len(delete_buttons) == 0:
                        logger.info("No more Delete buttons found")
                        break

                    # Click the first Delete button
                    first_delete = delete_buttons[0]
                    logger.info(f"Clearing item {cleared_count + 1} of {initial_count}...")

                    first_delete.click()

                    # Check for and handle any confirmation dialog/modal
                    time.sleep(1)

                    # Look for confirmation buttons (common patterns)
                    confirmation_selectors = [
                        "button:has-text('Delete')",  # Might be another Delete button in modal
                        "button:has-text('Confirm')",
                        "button:has-text('Yes')",
                        "button:has-text('OK')",
                        "button:has-text('Remove')",
                        "[role='dialog'] button",  # Any button in a dialog
                    ]

                    confirmed = False
                    for selector in confirmation_selectors:
                        try:
                            confirm_btn = self.page.locator(selector).first
                            if confirm_btn.is_visible(timeout=1000):
                                logger.debug(f"Found confirmation button: {selector}")
                                confirm_btn.click()
                                confirmed = True
                                break
                        except Exception:
                            continue

                    if not confirmed:
                        logger.debug("No confirmation dialog found")

                    cleared_count += 1

                    # Wait for the item to be removed and page to update
                    time.sleep(2)

                    # Safety check: prevent infinite loop
                    if cleared_count >= initial_count * 2:
                        logger.warning("Cleared more items than expected, stopping")
                        break

                except TimeoutError:
                    logger.info("Timeout waiting for delete button")
                    break
                except Exception as e:
                    logger.warning(f"Error clearing item: {e}")
                    break

            # Verify list is empty
            final_count = self._get_item_count()
            logger.info(f"Cleared {cleared_count} items, {final_count} remaining")

            if final_count == 0:
                logger.success("Amazon shopping list cleared successfully!")
                return True
            else:
                logger.warning(f"List not fully cleared: {final_count} items remaining")
                self._save_screenshot("amazon_list_not_cleared")
                return False

        except Exception as e:
            logger.error(f"Failed to clear Amazon list: {e}")
            self._save_screenshot("amazon_clear_error")
            raise Exception(f"Amazon list clearing failed: {e}")

    def clear_items_by_name(self, item_names: list[str]) -> dict:
        """Clear only specific items from Amazon shopping list by matching their name.

        Args:
            item_names: List of item name strings to delete (case-insensitive match)

        Returns:
            Dict with 'cleared' (list of names cleared) and 'not_found' (list of names not found)
        """
        logger.info(f"Clearing {len(item_names)} specific items from Amazon shopping list")

        result = {"cleared": [], "not_found": list(item_names)}

        try:
            # Navigate to shopping list
            self.page.goto(settings.amazon_list_url, wait_until="domcontentloaded")
            time.sleep(3)

            # Build a lowercase set of names we want to delete
            names_to_clear = {name.lower().strip() for name in item_names}
            cleared_names = set()

            # Find all Delete buttons and check each row's item name
            delete_buttons = self.page.locator("button:has-text('Delete')").all()
            logger.info(f"Found {len(delete_buttons)} items on the list, looking for {len(names_to_clear)} to clear")

            # We need to process buttons carefully since DOM shifts after each deletion.
            # Collect all item names first, then delete from bottom to top to avoid index shifts.
            items_to_delete = []

            for index, delete_btn in enumerate(delete_buttons):
                try:
                    item_name = delete_btn.evaluate("""
                        (button) => {
                            let current = button;
                            for (let i = 0; i < 10; i++) {
                                if (!current) return '';
                                current = current.parentElement;
                                if (!current) return '';

                                let editBtn = current.querySelector('button:not([aria-hidden])');
                                if (editBtn && editBtn.textContent.includes('Edit')) {
                                    let fullText = current.innerText || current.textContent || '';
                                    let lines = fullText.split('\\n').map(l => l.trim()).filter(l => l);

                                    for (let line of lines) {
                                        if (line === 'Edit' || line === 'Delete' ||
                                            line.includes('Show search') ||
                                            line.includes('Added') || line.includes('Edited') ||
                                            line.includes('ago')) {
                                            continue;
                                        }
                                        if (line.length > 2 && line.length < 100) {
                                            return line;
                                        }
                                    }
                                }
                            }
                            return '';
                        }
                    """)

                    if item_name and item_name.strip().lower() in names_to_clear:
                        items_to_delete.append((index, item_name.strip()))

                except Exception as e:
                    logger.warning(f"Error reading item at index {index}: {e}")
                    continue

            # Delete from bottom to top so DOM index shifts don't affect earlier items
            items_to_delete.reverse()

            for original_index, item_name in items_to_delete:
                try:
                    # Re-fetch buttons each time since DOM changes after deletion
                    current_buttons = self.page.locator("button:has-text('Delete')").all()

                    # Find the button for this item by re-scanning (positions shift)
                    deleted = False
                    for btn in current_buttons:
                        try:
                            btn_item_name = btn.evaluate("""
                                (button) => {
                                    let current = button;
                                    for (let i = 0; i < 10; i++) {
                                        if (!current) return '';
                                        current = current.parentElement;
                                        if (!current) return '';

                                        let editBtn = current.querySelector('button:not([aria-hidden])');
                                        if (editBtn && editBtn.textContent.includes('Edit')) {
                                            let fullText = current.innerText || current.textContent || '';
                                            let lines = fullText.split('\\n').map(l => l.trim()).filter(l => l);

                                            for (let line of lines) {
                                                if (line === 'Edit' || line === 'Delete' ||
                                                    line.includes('Show search') ||
                                                    line.includes('Added') || line.includes('Edited') ||
                                                    line.includes('ago')) {
                                                    continue;
                                                }
                                                if (line.length > 2 && line.length < 100) {
                                                    return line;
                                                }
                                            }
                                        }
                                    }
                                    return '';
                                }
                            """)

                            if btn_item_name and btn_item_name.strip().lower() == item_name.lower():
                                logger.info(f"Deleting '{item_name}'...")
                                btn.click()
                                time.sleep(2)
                                cleared_names.add(item_name.lower())
                                deleted = True
                                break

                        except Exception:
                            continue

                    if not deleted:
                        logger.warning(f"Could not find Delete button for '{item_name}' (may already be deleted)")

                except Exception as e:
                    logger.warning(f"Error deleting '{item_name}': {e}")

            result["cleared"] = [name for name in item_names if name.lower().strip() in cleared_names]
            result["not_found"] = [name for name in item_names if name.lower().strip() not in cleared_names]

            logger.info(f"Cleared {len(result['cleared'])}/{len(item_names)} items")
            if result["not_found"]:
                logger.warning(f"Could not find/clear: {result['not_found']}")

            return result

        except Exception as e:
            logger.error(f"Failed to clear specific items: {e}")
            self._save_screenshot("amazon_clear_specific_error")
            return result

    def clear_completed_items(self) -> int:
        """Clear only completed/checked items from the list.

        Returns:
            Number of items cleared
        """
        logger.info("Clearing completed items from Amazon shopping list")

        try:
            self.page.goto(settings.amazon_list_url, wait_until="domcontentloaded")
            time.sleep(3)

            # Look for "Clear completed" or similar button
            clear_completed_selectors = [
                "button:has-text('Clear completed')",
                "button:has-text('Remove completed')",
                "a:has-text('Clear completed')",
                "[data-action='clear-completed']",
            ]

            for selector in clear_completed_selectors:
                try:
                    clear_button = self.page.locator(selector).first
                    if clear_button.is_visible(timeout=2000):
                        initial_count = self._get_item_count()
                        clear_button.click()
                        logger.info("Clicked 'Clear completed' button")
                        time.sleep(2)

                        final_count = self._get_item_count()
                        cleared = initial_count - final_count
                        logger.success(f"Cleared {cleared} completed items")
                        return cleared
                except Exception:
                    continue

            logger.warning("Could not find 'Clear completed' button")
            return 0

        except Exception as e:
            logger.error(f"Failed to clear completed items: {e}")
            return 0

    def _get_item_count(self) -> int:
        """Get current count of items in the list by counting Delete buttons.

        Returns:
            Number of items
        """
        try:
            # Count Delete buttons (each item has one)
            count = self.page.locator("button:has-text('Delete')").count()
            return count
        except Exception:
            return 0

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
