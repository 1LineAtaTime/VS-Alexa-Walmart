"""Walmart product search using Playwright."""

import re
import time
import random
from typing import List, Dict, Any
from urllib.parse import quote_plus
from playwright.sync_api import Page, TimeoutError
from loguru import logger

from ..config import settings


class WalmartProductSearch:
    """Searches for products on Walmart.com."""

    def __init__(self, page: Page):
        """Initialize product search.

        Args:
            page: Authenticated Playwright page
        """
        self.page = page

    def search_products(
        self,
        query: str,
        max_results: int = 40
    ) -> List[Dict[str, Any]]:
        """Search for products on Walmart.

        Args:
            query: Search query (e.g., "2% milk")
            max_results: Maximum number of results to return

        Returns:
            List of product dictionaries

        Raises:
            Exception: If search fails
        """
        logger.info(f"Searching Walmart for: '{query}'")

        try:
            # Navigate to Walmart search with properly URL-encoded query
            encoded_query = quote_plus(query)
            search_url = f"{settings.walmart_base_url}/search?q={encoded_query}"
            self.page.goto(search_url, wait_until="domcontentloaded")
            logger.info(f"Navigated to: {search_url}")

            # Human-like random delay (2-4 seconds)
            delay = 2 + random.random() * 2
            logger.debug(f"Waiting {delay:.1f}s for page to load...")
            time.sleep(delay)

            # Check for bot detection and handle it
            self._handle_bot_detection()

            # Check if we got redirected to departments page instead of search results
            current_url = self.page.url
            if "/all-departments" in current_url:
                logger.warning(f"Redirected to departments page: {current_url}")
                logger.info("Attempting to navigate back to search results...")

                # Try to find and click a link that goes to search results
                # Or just reload with the search URL
                self.page.goto(search_url, wait_until="domcontentloaded")
                time.sleep(2)

                # Check again
                if "/all-departments" in self.page.url:
                    logger.error("Still on departments page after retry, cannot proceed")
                    self._save_screenshot("walmart_departments_redirect")
                    return []

                logger.success("Successfully navigated to search results")

            products = []

            # Wait for search results to load - try multiple selectors
            try:
                # Try multiple possible selectors for product items
                result_selectors = [
                    "[data-item-id]",
                    "[data-product-id]",
                    "[data-testid='item-stack']",
                    "[data-testid='list-view']",
                    "div[data-automation-id='product-title']",
                    "a[href*='/ip/']",  # Product links
                ]

                found = False
                for selector in result_selectors:
                    try:
                        self.page.wait_for_selector(selector, timeout=3000)
                        logger.debug(f"Found products using selector: {selector}")
                        found = True
                        break
                    except TimeoutError:
                        continue

                if not found:
                    logger.warning("No search results found with any selector, saving screenshot")
                    self._save_screenshot("walmart_search_no_results")
                    return []

            except TimeoutError:
                logger.warning("No search results found or page took too long to load")
                self._save_screenshot("walmart_search_timeout")
                return []

            # Scroll to load more results
            self._scroll_to_load_results()

            # Find all product cards first (div[@role='group'] containers)
            # This ensures we get products in visual order
            all_product_cards = self.page.locator("div[role='group']").all()
            logger.info(f"Found {len(all_product_cards)} product cards on page")

            # Extract products in order by iterating through cards
            product_data_by_id = {}

            # Limit cards processed to prevent memory buildup
            cards_to_process = all_product_cards[:max_results * 2]

            for card_index, card in enumerate(cards_to_process):  # Process more cards to ensure we get enough products
                try:
                    # First try to get ID directly from the card's data-item-id attribute
                    item_id = None
                    try:
                        item_id = card.get_attribute("data-item-id")
                        if item_id:
                            logger.debug(f"Card #{card_index+1}: Found data-item-id='{item_id}'")
                    except Exception:
                        pass

                    # Find the first product link within this card
                    link = card.locator("a[href*='/ip/']").first
                    if link.count() == 0:
                        continue

                    # Extract product data from the link
                    href = link.get_attribute("href")
                    if not href or "/ip/" not in href:
                        continue

                    # If we didn't get ID from data-item-id, extract from URL
                    if not item_id:
                        item_id = href.split("/")[-1].split("?")[0]

                    # Extract name from the link (it contains the span.w_iUH7)
                    name = ""
                    try:
                        name_span = link.locator("span.w_iUH7").first
                        if name_span.count() > 0:
                            name = name_span.inner_text(timeout=1000).strip()
                    except Exception:
                        pass

                    # Log every product we find for debugging
                    logger.debug(f"Card #{card_index+1}: Found product '{name}' (ID: {item_id})")

                    # Skip invalid IDs (must be alphanumeric and not "search")
                    if not item_id or item_id == "search" or len(item_id) < 3:
                        logger.debug(f"Skipping product with invalid ID '{item_id}': {name}")
                        continue

                    # Skip if we already have this product
                    if item_id in product_data_by_id:
                        logger.debug(f"Skipping duplicate product ID {item_id}: {name}")
                        continue

                    if not name:
                        logger.debug(f"Skipping product with no name (ID: {item_id})")
                        continue

                    # Now we have a valid product - store it with the card element
                    product_data_by_id[item_id] = {
                        "link_element": link,
                        "card_element": card,
                        "id": item_id,
                        "name": name,
                        "href": href,
                        "card_index": card_index
                    }
                    logger.debug(f"Added product to list: '{name}' (ID: {item_id})")

                    if len(product_data_by_id) >= max_results:
                        break

                except Exception as e:
                    logger.error(f"Error processing product card #{card_index+1}: {e}")
                    continue

            logger.info(f"Found {len(product_data_by_id)} unique products")

            # Now extract full product data for each unique product
            for index, (item_id, basic_data) in enumerate(product_data_by_id.items()):
                try:
                    link_element = basic_data["link_element"]
                    card_element = basic_data["card_element"]

                    # Extract complete product data using the card element we already have
                    product_data = self._extract_product_data_from_link(
                        link_element=link_element,
                        parent_element=card_element,
                        item_id=item_id,
                        name=basic_data["name"],
                        href=basic_data["href"],
                        index=basic_data["card_index"]  # Use original card index for position tracking
                    )

                    if product_data:
                        products.append(product_data)
                except Exception as e:
                    logger.debug(f"Failed to parse product {index} ({basic_data.get('name', 'unknown')}): {e}")
                    continue

            # Sort by bought_count (highest first), then by price (lowest first)
            products.sort(key=lambda x: (x.get('bought_count', 0), -x.get('price', 999999)), reverse=True)

            # Memory leak prevention: Clear large locator references
            del all_product_cards
            del cards_to_process
            del product_data_by_id

            logger.success(f"Found {len(products)} products for '{query}'")

            # Log all extracted products for debugging
            logger.info("All extracted products:")
            for idx, p in enumerate(products):
                logger.info(f"  {idx+1}. {p['name']} (ID: {p['id']}, Bought: {p.get('bought_count', 0)}+)")

            if products and products[0].get('bought_count', 0) > 0:
                logger.info(f"Top result: {products[0]['name']} (Bought {products[0]['bought_count']}+ times, ${products[0]['price']})")
            return products

        except Exception as e:
            logger.error(f"Search failed: {e}")
            self._save_screenshot("walmart_search_error")
            raise Exception(f"Product search failed: {e}")

    def find_product_element_by_id(self, item_id: str):
        """Find the product card element on the current search results page by item ID.

        Args:
            item_id: Walmart product/item ID

        Returns:
            Playwright element for the product card, or None if not found
        """
        try:
            # Find the product card by its data-item-id or by looking for links containing the item_id
            product_card_selectors = [
                f"div[data-item-id*='{item_id}']",
                f"div[data-dca-id*='{item_id}']",
                f"a[href*='/ip/{item_id}']"
            ]

            product_card = None
            for selector in product_card_selectors:
                try:
                    element = self.page.locator(selector).first
                    if element.count() > 0:
                        # If we found a link, go up to the parent product card
                        if 'a[href' in selector:
                            # Go up to find the product card container
                            product_card = element.locator("xpath=ancestor::div[@role='group']").first
                            if product_card.count() > 0:
                                logger.info(f"Found product card for item {item_id}")
                                break
                        else:
                            logger.info(f"Found product card for item {item_id}")
                            product_card = element
                            break
                except Exception:
                    continue

            if not product_card:
                logger.warning(f"Could not find product card for item {item_id} on search page")
                return None

            # IMPORTANT: Wait for the Add button to be present within this card
            # This ensures the card is fully loaded before we return it
            try:
                logger.info(f"Waiting for Add button to be present in product card for item {item_id}...")
                add_button = product_card.locator("button[data-automation-id='add-to-cart']").first
                add_button.wait_for(state="attached", timeout=5000)
                logger.info(f"Add button is present in product card for item {item_id}")
            except Exception as e:
                logger.warning(f"Add button not found in product card after 5 seconds: {e}")
                # Still return the card, the cart_manager will handle this with better error messages

            return product_card

        except Exception as e:
            logger.error(f"Error finding product element: {e}")
            return None

    def _extract_product_data_from_link(
        self,
        link_element,
        parent_element,
        item_id: str,
        name: str,
        href: str,
        index: int
    ) -> Dict[str, Any]:
        """Extract product data from link element and its parent container.

        Args:
            link_element: Link element containing product name
            parent_element: Parent container with price, stock, etc.
            item_id: Product ID already extracted
            name: Product name already extracted
            href: Product URL already extracted
            index: Product index

        Returns:
            Product data dictionary or None
        """
        try:
            # Build full product URL
            product_url = f"{settings.walmart_base_url}{href.split('?')[0]}"

            # Extract price from parent container
            price = 0.0
            price_selectors = [
                "[data-automation-id='product-price']",
                ".price-main",
                "[aria-label*='current price']",
                "span[itemprop='price']",
                ".price-characteristic",
                "div[data-automation-id='product-price'] span"
            ]

            for selector in price_selectors:
                try:
                    price_elem = parent_element.locator(selector).first
                    if price_elem.count() > 0 and price_elem.is_visible(timeout=500):
                        price_text = price_elem.inner_text(timeout=500).strip()
                        # Extract numeric value
                        price_text = price_text.replace("$", "").replace(",", "").replace("¢", "").strip()
                        # Get first number (current price)
                        import re
                        match = re.search(r'(\d+\.?\d*)', price_text)
                        if match:
                            price = float(match.group(1))
                            if price > 0:
                                break
                except Exception:
                    continue

            # Extract "Bought x times" count from parent
            bought_count = 0
            try:
                bought_elem = parent_element.locator("text=/Bought .* time/i").first
                if bought_elem.count() > 0 and bought_elem.is_visible(timeout=500):
                    bought_text = bought_elem.inner_text()
                    match = re.search(r'Bought (\d+)\+?', bought_text, re.IGNORECASE)
                    if match:
                        bought_count = int(match.group(1))
                        logger.debug(f"Found 'Bought {bought_count}+ times' for {name}")
            except Exception:
                pass

            # Extract stock status
            in_stock = True
            try:
                out_of_stock_selectors = [
                    "text='Out of stock'",
                    "text='Sold out'",
                    "text='Unavailable'"
                ]
                for selector in out_of_stock_selectors:
                    if parent_element.locator(selector).count() > 0:
                        in_stock = False
                        break
            except Exception:
                pass

            # Extract image URL
            image_url = None
            try:
                img_elem = parent_element.locator("img").first
                if img_elem.count() > 0:
                    image_url = img_elem.get_attribute("src")
            except Exception:
                pass

            product = {
                "id": item_id,
                "name": name,
                "price": price,
                "in_stock": in_stock,
                "image": image_url,
                "product_url": product_url,
                "bought_count": bought_count,
                "frequently_bought": bought_count > 0,
                "search_position": index  # Position in search results (lower = better)
            }

            logger.debug(f"Extracted product: {name} (${price}, Bought {bought_count}+ times)")
            return product

        except Exception as e:
            logger.warning(f"Error extracting product data from link: {e}")
            return None

    def _extract_product_data(self, element, index: int) -> Dict[str, Any]:
        """Extract product data from element.

        Args:
            element: Playwright locator element
            index: Product index

        Returns:
            Product data dictionary or None
        """
        try:
            # Extract item ID from link
            item_id = None
            product_link = None
            try:
                # Look for link with pattern /ip/Product-Name/12345
                link = element.locator("a[href*='/ip/']").first
                href = link.get_attribute("href")
                if href and "/ip/" in href:
                    # Extract ID from URL like /ip/Product-Name/123456
                    item_id = href.split("/")[-1].split("?")[0]
                    product_link = f"{settings.walmart_base_url}{href.split('?')[0]}"
            except Exception as e:
                logger.debug(f"Could not extract link for product {index}: {e}")

            # Try alternative methods for item ID
            if not item_id:
                try:
                    item_id = element.get_attribute("data-item-id")
                    if not item_id:
                        item_id = element.get_attribute("data-product-id")
                    if not item_id:
                        # Try link-identifier attribute
                        link_id = element.locator("a[link-identifier]").first.get_attribute("link-identifier")
                        if link_id:
                            item_id = link_id
                except Exception:
                    pass

            if not item_id:
                logger.debug(f"Could not find item ID for product {index}")
                return None

            # Extract product name - look for span with class w_iUH7 first (primary name)
            name = ""
            name_selectors = [
                "span.w_iUH7",  # Primary product name span
                "[data-automation-id='product-title']",
                ".product-title",
                "a[link-identifier] span",
                "span[itemprop='name']",
            ]

            for selector in name_selectors:
                try:
                    name_elem = element.locator(selector).first
                    if name_elem.is_visible(timeout=1000):
                        name = name_elem.inner_text(timeout=1000).strip()
                        if name:
                            break
                except Exception:
                    continue

            if not name:
                logger.debug(f"Could not find name for product {index}")
                return None

            # Extract price
            price = 0.0
            price_selectors = [
                "[data-automation-id='product-price']",
                ".price-main",
                "[aria-label*='current price']",
                "span[itemprop='price']",
                ".price-characteristic"
            ]

            for selector in price_selectors:
                try:
                    price_elem = element.locator(selector).first
                    if price_elem.is_visible(timeout=1000):
                        price_text = price_elem.inner_text(timeout=1000).strip()
                        # Extract numeric value
                        price_text = price_text.replace("$", "").replace(",", "").strip()
                        # Get first number (current price)
                        price = float(price_text.split()[0])
                        if price > 0:
                            break
                except Exception:
                    continue

            # Extract stock status
            in_stock = True
            try:
                out_of_stock_selectors = [
                    "text='Out of stock'",
                    "text='Sold out'",
                    "text='Unavailable'",
                    "[data-automation-id='out-of-stock']"
                ]

                for selector in out_of_stock_selectors:
                    if element.locator(selector).is_visible(timeout=500):
                        in_stock = False
                        break
            except Exception:
                pass

            # Extract image URL
            image_url = None
            try:
                img_elem = element.locator("img").first
                image_url = img_elem.get_attribute("src")
            except Exception:
                pass

            # Build product URL
            product_url = f"{settings.walmart_base_url}/ip/{item_id}"

            # Extract "Bought x times" count
            bought_count = 0
            try:
                # Look for text like "Bought 5+ times" or "Bought 4 times"
                bought_elem = element.locator("text=/Bought .* time/i").first
                if bought_elem.is_visible(timeout=500):
                    bought_text = bought_elem.inner_text()
                    # Extract number, handle "5+" format
                    match = re.search(r'Bought (\d+)\+?', bought_text, re.IGNORECASE)
                    if match:
                        bought_count = int(match.group(1))
                        logger.debug(f"Found 'Bought {bought_count}+ times' for {name}")
            except Exception:
                pass

            # Check for badges (frequently bought, etc.)
            frequently_bought = bought_count > 0  # Prioritize items with purchase history
            try:
                badge_selectors = [
                    "text='Frequently bought'",
                    "text='Popular pick'",
                    "text='Best seller'",
                    "[data-automation-id='badge']"
                ]

                for selector in badge_selectors:
                    if element.locator(selector).is_visible(timeout=500):
                        frequently_bought = True
                        break
            except Exception:
                pass

            product = {
                "id": item_id,
                "name": name,
                "price": price,
                "in_stock": in_stock,
                "image": image_url,
                "product_url": product_url,
                "bought_count": bought_count,  # NEW: track purchase frequency
                "frequently_bought": frequently_bought
            }

            logger.debug(f"Extracted product: {name} (${price})")
            return product

        except Exception as e:
            logger.warning(f"Error extracting product data: {e}")
            return None

    def _scroll_to_load_results(self) -> None:
        """Scroll page to trigger lazy loading of more results."""
        try:
            # Scroll down in increments
            for _ in range(3):
                self.page.evaluate("window.scrollBy(0, 1000)")
                time.sleep(0.5)

            # Scroll back to top
            self.page.evaluate("window.scrollTo(0, 0)")
            time.sleep(0.5)

        except Exception as e:
            logger.debug(f"Error during scroll: {e}")

    def search_my_items(self, max_pages: int = 10) -> List[Dict[str, Any]]:
        """Search through Walmart My Items (previously purchased items).

        Args:
            max_pages: Maximum number of pages to check

        Returns:
            List of product dictionaries from My Items
        """
        logger.info("Searching Walmart My Items for previously purchased products")

        all_items = []

        try:
            for page_num in range(1, max_pages + 1):
                my_items_url = f"{settings.walmart_base_url}/my-items?filter=All&page={page_num}"
                logger.info(f"Checking My Items page {page_num}: {my_items_url}")

                self.page.goto(my_items_url, wait_until="domcontentloaded")
                time.sleep(2)

                # Check if we're still on my-items page (not redirected to login)
                if "my-items" not in self.page.url:
                    logger.warning("Redirected away from My Items, may need to re-authenticate")
                    break

                # Wait for items to load
                try:
                    self.page.wait_for_selector(
                        "[data-item-id], [data-product-id], .my-items-tile",
                        timeout=5000
                    )
                except TimeoutError:
                    logger.info(f"No items found on page {page_num}, stopping")
                    break

                # Get all product elements on this page
                product_elements = self.page.locator(
                    "[data-item-id], [data-product-id], .my-items-tile"
                ).all()

                if not product_elements:
                    logger.info(f"No more items on page {page_num}")
                    break

                logger.info(f"Found {len(product_elements)} items on page {page_num}")

                # Extract product data
                for index, element in enumerate(product_elements):
                    try:
                        product_data = self._extract_product_data(element, index)
                        if product_data:
                            # Mark as from My Items for priority matching
                            product_data["from_my_items"] = True
                            # Store which page this was found on
                            product_data["my_items_page"] = page_num
                            all_items.append(product_data)
                    except Exception as e:
                        logger.debug(f"Failed to parse My Items product {index}: {e}")
                        continue

                # Small delay between pages
                time.sleep(1)

            logger.success(f"Found {len(all_items)} total items in My Items")
            return all_items

        except Exception as e:
            logger.error(f"Failed to search My Items: {e}")
            self._save_screenshot("walmart_my_items_error")
            return []

    def _handle_bot_detection(self) -> None:
        """Handle Walmart's 'Press & Hold' bot detection challenge."""
        try:
            time.sleep(2)

            # Check if bot detection challenge is present
            robot_check_text = self.page.locator("text='Robot or human?'").first
            if robot_check_text.count() > 0 and robot_check_text.is_visible(timeout=2000):
                logger.info("Bot detection challenge detected! Handling Press & Hold...")

                # Find the Press & Hold button
                btn_locator = self.page.locator("button").first
                if btn_locator.count() > 0 and btn_locator.is_visible(timeout=2000):
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
        except Exception as e:
            logger.debug(f"No bot detection to handle or error: {e}")

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
