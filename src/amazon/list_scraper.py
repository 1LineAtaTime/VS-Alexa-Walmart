"""Amazon shopping list scraper."""

import time
from typing import List, Dict, Any
from playwright.sync_api import Page, TimeoutError
from loguru import logger

from ..config import settings


class AmazonListScraper:
    """Scrapes items from Amazon Alexa shopping list."""

    def __init__(self, page: Page):
        """Initialize list scraper.

        Args:
            page: Authenticated Playwright page
        """
        self.page = page

    def scrape_list(self) -> List[Dict[str, Any]]:
        """Scrape all items from Amazon shopping list.

        Returns:
            List of items with their details

        Raises:
            Exception: If scraping fails
        """
        logger.info("Scraping Amazon shopping list")

        try:
            # Only navigate if we're not already on the shopping list page
            current_url = self.page.url
            if "alexa-shopping-list" not in current_url:
                logger.info("Not on shopping list page, navigating...")
                self.page.goto(settings.amazon_list_url, wait_until="domcontentloaded")
                logger.info(f"Navigated to {settings.amazon_list_url}")
                time.sleep(3)  # Wait for dynamic content to load
            else:
                logger.debug("Already on shopping list page, skipping navigation")

            # Look for the list container
            # Amazon's Alexa shopping list typically uses specific data attributes
            # We'll try multiple selectors to be robust

            items = []

            # Method 1: Simple approach - find item names by looking for specific text patterns
            try:
                # Wait for the page to load - look for the Alexa Shopping List heading
                try:
                    self.page.wait_for_selector("text='Alexa Shopping List'", timeout=5000)
                    logger.info("Page loaded - found Alexa Shopping List heading")
                except TimeoutError:
                    logger.warning("Could not find heading, continuing anyway")

                time.sleep(3)  # Give extra time for dynamic content to load

                # Find all Delete buttons (one per item)
                delete_buttons = self.page.locator("button:has-text('Delete')").all()
                logger.info(f"Found {len(delete_buttons)} Delete buttons")

                if not delete_buttons or len(delete_buttons) == 0:
                    logger.warning("No Delete buttons found - list may be empty")
                    raise TimeoutError("No Delete buttons found")

                # For each Delete button, extract the item name from the same row
                for index, delete_btn in enumerate(delete_buttons):
                    try:
                        # Navigate up to find the parent container that has all row info
                        # The item name should be in the same container as the Delete button

                        # Get the row that contains this delete button and extract just the item name
                        item_name = delete_btn.evaluate("""
                            (button) => {
                                // Go up to find the parent row - look for one that has both Edit and Delete
                                let current = button;
                                for (let i = 0; i < 10; i++) {
                                    if (!current) return '';
                                    current = current.parentElement;
                                    if (!current) return '';

                                    // Check if this level has Edit button (sibling to Delete)
                                    let editBtn = current.querySelector('button:not([aria-hidden])');
                                    if (editBtn && editBtn.textContent.includes('Edit')) {
                                        // We found the row level - now get all text
                                        let fullText = current.innerText || current.textContent || '';

                                        // Split by newlines and find the item name (first substantial line)
                                        let lines = fullText.split('\\n').map(l => l.trim()).filter(l => l);

                                        for (let line of lines) {
                                            // Skip button text and metadata
                                            if (line === 'Edit' || line === 'Delete' ||
                                                line.includes('Show search') ||
                                                line.includes('Added') || line.includes('Edited') ||
                                                line.includes('ago')) {
                                                continue;
                                            }
                                            // This should be the item name
                                            if (line.length > 2 && line.length < 100) {
                                                return line;
                                            }
                                        }
                                    }
                                }
                                return '';
                            }
                        """)

                        logger.debug(f"Row {index} item: {item_name}")

                        if not item_name or len(item_name.strip()) == 0:
                            logger.warning(f"Could not extract item name from row {index}")
                            continue

                        item_name = item_name.strip()

                        items.append({
                            "name": item_name,
                            "quantity": 1,  # Alexa shopping list doesn't show quantities explicitly
                            "raw_text": item_name,  # Store the item name as raw text
                            "index": index
                        })

                        logger.info(f"Scraped item {index + 1}: {item_name}")

                    except Exception as e:
                        logger.warning(f"Failed to parse item {index}: {e}")
                        continue

            except TimeoutError:
                logger.warning("Could not find standard list items, trying alternative method")

                # Method 2: Try to get list from page content
                page_content = self.page.content()

                # Look for specific patterns in the HTML
                # This is a fallback and might need adjustment based on actual page structure
                logger.info("Using fallback scraping method")

            # Method 3: Check if list is empty
            if not items:
                # Look for empty list indicators
                empty_indicators = [
                    "text='Your list is empty'",
                    "text='No items'",
                    "text='Add items to your list'",
                    ".empty-list",
                ]

                for indicator in empty_indicators:
                    try:
                        if self.page.locator(indicator).is_visible(timeout=2000):
                            logger.info("Shopping list is empty")
                            return []
                    except Exception:
                        continue

                # If we get here and still have no items, assume list is empty
                # (avoiding unnecessary screenshots during routine checks)
                logger.info("No items found in shopping list, assuming empty")
                return []

            logger.success(f"Scraped {len(items)} items from Amazon shopping list")
            return items

        except Exception as e:
            logger.error(f"Failed to scrape Amazon list: {e}")
            self._save_screenshot("amazon_list_error")
            raise Exception(f"Amazon list scraping failed: {e}")

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

    def get_list_count(self) -> int:
        """Get count of items in shopping list.

        Returns:
            Number of items in list
        """
        try:
            self.page.goto(settings.amazon_list_url, wait_until="domcontentloaded")
            time.sleep(2)

            # Count items
            item_count = self.page.locator(
                ".mls-item, [data-testid*='list-item'], .shopping-list-item"
            ).count()

            logger.info(f"Shopping list has {item_count} items")
            return item_count

        except Exception as e:
            logger.error(f"Failed to get list count: {e}")
            return 0
