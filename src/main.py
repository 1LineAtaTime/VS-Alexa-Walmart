"""Main orchestration script for Amazon-Walmart automation."""

import os
import sys
import time
import signal
import argparse
import random
from pathlib import Path
from typing import Optional
from datetime import datetime

# Add parent directory to path so we can import src modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright, Browser, Page, TimeoutError
from loguru import logger

from src.config import settings
from src.utils import setup_logger
from src.auth import AmazonAuthenticator, WalmartAuthenticator
from src.amazon import AmazonListScraper, AmazonListClearer
from src.walmart import WalmartProductSearch, WalmartCartManager
from src.search.matcher import ItemMatcher


class AmazonWalmartAutomation:
    """Main automation orchestrator with persistent browser sessions."""

    def __init__(self, headless: Optional[bool] = None):
        """Initialize the automation.

        Args:
            headless: Override browser headless setting (None = use settings.browser_headless)
        """
        # Setup logging
        setup_logger(
            log_level=settings.log_level,
            log_dir=settings.log_dir
        )

        self.playwright = None
        self.browser: Optional[Browser] = None
        self.amazon_auth: Optional[AmazonAuthenticator] = None
        self.walmart_auth: Optional[WalmartAuthenticator] = None

        # Persistent pages (kept open between runs)
        self.amazon_page: Optional[Page] = None
        self.walmart_page: Optional[Page] = None

        self.should_stop = False

        # Track whether we've done initial Walmart authentication
        self.walmart_initially_authenticated = False

        # Store headless preference (None = use config, True/False = override)
        self.headless = headless if headless is not None else settings.browser_headless

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.should_stop = True
        self.cleanup()
        sys.exit(0)

    def run_once(self) -> bool:
        """Run the automation workflow once.

        Returns:
            True if workflow completed successfully
        """
        logger.info("="*70)
        logger.info("STARTING AMAZON TO WALMART AUTOMATION")
        logger.info("="*70)

        try:
            # Initialize browser if not already done
            if not self.browser:
                self._init_browser()

            # Authenticate with Amazon if not already done
            if not self.amazon_page:
                logger.info("\n" + "="*70)
                logger.info("STEP 1: AMAZON AUTHENTICATION")
                logger.info("="*70)
                self.amazon_page = self._authenticate_amazon()

            # Scrape Amazon shopping list FIRST (before opening Walmart)
            logger.info("\n" + "="*70)
            logger.info("STEP 2: SCRAPING AMAZON SHOPPING LIST")
            logger.info("="*70)
            amazon_scraper = AmazonListScraper(self.amazon_page)
            items = amazon_scraper.scrape_list()

            if not items:
                logger.info("No items in Amazon shopping list.")

                # On first run, authenticate with Walmart to verify it works
                if not self.walmart_initially_authenticated:
                    logger.info("\n" + "="*70)
                    logger.info("INITIAL WALMART AUTHENTICATION (First Run)")
                    logger.info("="*70)
                    logger.info("Authenticating with Walmart to verify credentials...")
                    self.walmart_page = self._authenticate_walmart()
                    self.walmart_initially_authenticated = True
                    logger.success("Walmart authentication verified successfully")

                    # Close Walmart page immediately since we don't need it yet
                    logger.info("Closing Walmart page (will reopen when items are found)...")
                    self._close_walmart()
                else:
                    # Close Walmart page to save resources (will reopen when items are found)
                    if self.walmart_page:
                        logger.info("Closing Walmart page to save resources...")
                        self._close_walmart()

                logger.info(f"Keeping Amazon browser open, will check again in {settings.schedule_interval_min_minutes}-{settings.schedule_interval_max_minutes} minutes...")
                return True

            logger.success(f"Found {len(items)} items in Amazon shopping list:")
            for i, item in enumerate(items, 1):
                logger.info(f"  {i}. {item['name']} (qty: {item['quantity']})")

            # Save items to .txt file
            logger.info("\n" + "="*70)
            logger.info("STEP 3: SAVING ITEMS TO FILE")
            logger.info("="*70)
            txt_file = self._save_items_to_file(items)
            logger.success(f"Items saved to: {txt_file}")

            # Clear Amazon shopping list immediately
            logger.info("\n" + "="*70)
            logger.info("STEP 4: CLEARING AMAZON SHOPPING LIST")
            logger.info("="*70)
            amazon_clearer = AmazonListClearer(self.amazon_page)
            if amazon_clearer.clear_list():
                logger.success("Amazon shopping list cleared successfully")
            else:
                logger.warning("Failed to fully clear Amazon shopping list")

            # Check if we should skip Walmart and stop here
            skip_walmart = os.getenv("SKIP_WALMART", "false").lower() == "true"

            if skip_walmart:
                logger.info("\n" + "="*70)
                logger.info("SKIPPING WALMART (SKIP_WALMART=true)")
                logger.info("="*70)
                logger.info("Amazon workflow completed successfully!")
                logger.info(f"  - Scraped {len(items)} items from Alexa Shopping List")
                logger.info(f"  - Saved items to: {txt_file}")
                logger.info("  - Cleared Amazon list")
                logger.info("="*70)

                # Delete the .txt file since we're done
                if txt_file and Path(txt_file).exists():
                    try:
                        Path(txt_file).unlink()
                        logger.success(f"Deleted shopping list file: {txt_file}")
                    except Exception as e:
                        logger.warning(f"Failed to delete shopping list file: {e}")

                logger.success("AUTOMATION COMPLETED!")
                logger.info("="*70 + "\n")
                return True

            # Process each item from the saved file
            logger.info("\n" + "="*70)
            logger.info("STEP 5: WALMART AUTHENTICATION & ADDING ITEMS TO CART")
            logger.info("="*70)

            # Authenticate with Walmart now that we have items to process
            if not self.walmart_page:
                logger.info("Authenticating with Walmart...")
                self.walmart_page = self._authenticate_walmart()
                self.walmart_initially_authenticated = True
                logger.success("Walmart authentication successful")
            else:
                logger.info("Using existing Walmart session...")

            walmart_search = WalmartProductSearch(self.walmart_page)
            walmart_cart = WalmartCartManager(self.walmart_page)

            successfully_added = []  # Track which items were successfully added
            failed_items = []
            items_needing_fallback = []  # Items that failed to add from search - will try My Items in batch

            # Process each item - go directly to catalog search
            for i, item in enumerate(items, 1):
                logger.info(f"\n--- Processing item {i}/{len(items)}: {item['name']} ---")

                try:
                    # Search Walmart catalog directly
                    logger.info(f"Searching Walmart catalog for '{item['name']}'...")
                    products = walmart_search.search_products(
                        query=item['name'],
                        max_results=40
                    )

                    if not products:
                        logger.warning(f"No products found for '{item['name']}'")
                        failed_items.append(item)  # Append the full item dict, not just name
                        continue

                    # Products are already sorted by bought_count (highest first)
                    # Just pick the first item (highest "Bought N+ times")
                    # This is more reliable than fuzzy string matching!
                    logger.info(f"Selecting top product (highest purchase frequency)...")

                    # Get the first product (highest bought count)
                    top_product = products[0]

                    logger.info(f"Selected: {top_product['name']}")
                    logger.info(f"  Item ID: {top_product['id']}")
                    logger.info(f"  Price: ${top_product['price']}")
                    logger.info(f"  Bought Count: {top_product.get('bought_count', 0)}")
                    logger.info(f"  In Stock: {top_product.get('in_stock', True)}")

                    # Check if in stock
                    if not top_product.get('in_stock', True):
                        logger.warning(f"Product is out of stock, skipping")
                        failed_items.append(item)
                        continue

                    # Find the product element on the search page
                    logger.info("Finding product card on search page...")
                    product_element = walmart_search.find_product_element_by_id(top_product['id'])

                    if not product_element:
                        logger.error(f"Could not find product card on search page for {top_product['id']}")
                        failed_items.append(item)
                        continue

                    # Add to cart using the product element (stays on search page)
                    logger.info("Adding to Walmart cart from search results...")
                    success = walmart_cart.add_to_cart(
                        item_id=top_product['id'],
                        quantity=item['quantity'],
                        product_element=product_element
                    )

                    if success:
                        logger.success(f"✓ Added '{top_product['name']}' to cart")
                        successfully_added.append(item)  # Track successfully added items
                    else:
                        logger.warning(f"✗ Failed to add '{top_product['name']}' from search results")
                        logger.info(f"Will try My Items fallback after processing all items...")
                        # Store for batch My Items fallback later
                        items_needing_fallback.append({
                            'item': item,
                            'top_product': top_product
                        })

                    # Small delay between items
                    time.sleep(settings.search_delay)

                except Exception as e:
                    logger.error(f"Error processing '{item['name']}': {e}")
                    failed_items.append(item)
                    continue

            # BATCH MY ITEMS FALLBACK - Process all failed items at once
            if items_needing_fallback:
                logger.info("\n" + "="*70)
                logger.info("MY ITEMS FALLBACK - Batch Processing")
                logger.info("="*70)
                logger.info(f"{len(items_needing_fallback)} item(s) failed to add from search results")
                logger.info("Searching My Items once for all failed items...")

                try:
                    # Search My Items pages ONCE (up to 10 pages)
                    my_items = walmart_search.search_my_items(max_pages=10)

                    if my_items:
                        logger.success(f"Found {len(my_items)} items in My Items")
                        logger.info("\nMatching failed items against My Items...")

                        # Use fuzzy matching with higher threshold for My Items
                        matcher = ItemMatcher(
                            min_score=60,  # Higher threshold to avoid false positives
                            prefer_frequent=True
                        )

                        # Match each failed item against My Items collection
                        matches_to_add = []
                        for fallback_info in items_needing_fallback:
                            item = fallback_info['item']
                            top_product = fallback_info['top_product']

                            logger.info(f"\nMatching '{item['name']}'...")
                            logger.info(f"  Using product name: '{top_product['name']}'")

                            match = matcher.find_best_match(
                                query=top_product['name'],  # Use product name for better matching
                                items=my_items
                            )

                            if match:
                                logger.success(f"  ✓ Match found: {match.item_name} (score: {match.score}, page: {match.my_items_page})")
                                matches_to_add.append({
                                    'item': item,
                                    'match': match
                                })
                            else:
                                logger.warning(f"  ✗ No good match found (threshold: 60)")
                                failed_items.append(item)

                        # Now add all matched items by navigating to their specific pages
                        if matches_to_add:
                            logger.info(f"\n{len(matches_to_add)} match(es) found. Adding to cart...")

                            for idx, match_info in enumerate(matches_to_add, 1):
                                item = match_info['item']
                                match = match_info['match']

                                logger.info(f"\n[{idx}/{len(matches_to_add)}] Adding '{match.item_name}'...")

                                try:
                                    # Navigate to the specific My Items page
                                    if hasattr(match, 'my_items_page') and match.my_items_page:
                                        my_items_url = f"{settings.walmart_base_url}/my-items?filter=All&page={match.my_items_page}"
                                        logger.info(f"  Navigating to My Items page {match.my_items_page}...")
                                        self.walmart_page.goto(my_items_url, wait_until="domcontentloaded")
                                        time.sleep(3)

                                    # Find the product element
                                    product_element = walmart_search.find_product_element_by_id(match.item_id)

                                    if product_element:
                                        # Try adding from My Items
                                        success = walmart_cart.add_to_cart(
                                            item_id=match.item_id,
                                            quantity=item['quantity'],
                                            product_element=product_element
                                        )

                                        if success:
                                            logger.success(f"  ✓ Added '{match.item_name}' from My Items!")
                                            successfully_added.append(item)
                                        else:
                                            logger.error(f"  ✗ Failed to add from My Items")
                                            failed_items.append(item)
                                    else:
                                        logger.error(f"  ✗ Could not find product element on page")
                                        failed_items.append(item)

                                except Exception as e:
                                    logger.error(f"  ✗ Error adding from My Items: {e}")
                                    failed_items.append(item)

                                time.sleep(2)  # Small delay between adds
                        else:
                            logger.warning("No matches found for any failed items")
                            failed_items.extend([f['item'] for f in items_needing_fallback])

                    else:
                        logger.warning("No items found in My Items")
                        failed_items.extend([f['item'] for f in items_needing_fallback])

                except Exception as e:
                    logger.error(f"Error during My Items batch fallback: {e}")
                    failed_items.extend([f['item'] for f in items_needing_fallback])

            # Summary
            logger.info("\n" + "="*70)
            logger.info("AUTOMATION SUMMARY")
            logger.info("="*70)
            logger.info(f"Total items processed: {len(items)}")
            logger.info(f"Successfully added to cart: {len(successfully_added)}")
            logger.info(f"Failed to add: {len(failed_items)}")

            if failed_items:
                logger.warning("Failed items:")
                for item in failed_items:
                    logger.warning(f"  - {item['name']}")

            logger.info("="*70)
            logger.success("AUTOMATION COMPLETED!")
            logger.info("="*70 + "\n")

            # Handle .txt file based on success
            if txt_file and Path(txt_file).exists():
                if len(successfully_added) == len(items):
                    # All items added successfully - delete the file
                    try:
                        Path(txt_file).unlink()
                        logger.success(f"All items added! Deleted shopping list file: {txt_file}")
                    except Exception as e:
                        logger.warning(f"Failed to delete shopping list file: {e}")
                elif len(successfully_added) > 0:
                    # Some items added - remove only successful items from file
                    try:
                        self._remove_items_from_file(txt_file, successfully_added)
                        logger.info(f"Updated shopping list file: removed {len(successfully_added)} successful items")
                        logger.info(f"Remaining items in file: {len(failed_items)}")
                    except Exception as e:
                        logger.warning(f"Failed to update shopping list file: {e}")
                else:
                    # No items added - keep the file as is
                    logger.info(f"No items added to cart. Keeping shopping list file: {txt_file}")

            # Close Walmart page to save resources until next items are found
            logger.info("\nClosing Walmart page to save resources...")
            self._close_walmart()
            logger.info("Walmart page closed. Will reopen when new items are found.")

            return True

        except Exception as e:
            logger.error(f"Automation failed: {e}", exc_info=True)
            return False

    def run_scheduled(self) -> None:
        """Run automation on a schedule (random interval) with persistent browser."""
        logger.info(f"Starting scheduled automation (random interval: {settings.schedule_interval_min_minutes}-{settings.schedule_interval_max_minutes} minutes)")
        logger.info("Browsers will stay open between runs to save resources")
        logger.info("Press Ctrl+C to stop")

        # Initialize browser once
        self._init_browser()

        # Authenticate with Amazon only (Walmart will open on-demand when items are found)
        logger.info("Initial Amazon authentication...")
        self.amazon_page = self._authenticate_amazon()
        logger.success("Amazon authentication complete")
        logger.info("Walmart will authenticate only when items are found in the shopping list")

        while not self.should_stop:
            try:
                # Run automation (browsers stay open)
                self.run_once()

                # Wait for next run with random interval
                if not self.should_stop:
                    # Generate random wait time between min and max
                    wait_minutes = random.randint(
                        settings.schedule_interval_min_minutes,
                        settings.schedule_interval_max_minutes
                    )
                    wait_seconds = wait_minutes * 60

                    logger.info(f"\nBrowsers staying open...")
                    logger.info(f"Waiting {wait_minutes} minutes until next run (random interval: {settings.schedule_interval_min_minutes}-{settings.schedule_interval_max_minutes} min)...")
                    logger.info(f"Next run at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + wait_seconds))}\n")

                    # Sleep in small increments to allow for interruption
                    for _ in range(wait_seconds):
                        if self.should_stop:
                            break
                        time.sleep(1)

            except KeyboardInterrupt:
                logger.info("\nReceived interrupt signal")
                break
            except Exception as e:
                logger.error(f"Error in scheduled run: {e}")
                logger.warning("Will retry in 60 seconds...")
                time.sleep(60)

        logger.info("Scheduled automation stopped")
        self.cleanup()

    def _init_browser(self) -> None:
        """Initialize Playwright browser."""
        logger.info("Initializing browser...")

        self.playwright = sync_playwright().start()

        # Launch browser with anti-detection measures
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            channel="chrome",  # Use Chrome instead of Chromium (more common)
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-setuid-sandbox",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu",
                "--window-size=1920,1080",
                "--start-maximized",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
            ]
        )

        logger.success(f"Browser launched (headless={self.headless})")

    def _authenticate_amazon(self):
        """Authenticate with Amazon.

        Returns:
            Authenticated Playwright page
        """
        logger.info("Authenticating with Amazon...")
        self.amazon_auth = AmazonAuthenticator(self.browser)
        page = self.amazon_auth.authenticate()
        logger.success("Amazon authentication successful")
        return page

    def _authenticate_walmart(self):
        """Authenticate with Walmart.

        Returns:
            Authenticated Playwright page
        """
        logger.info("Authenticating with Walmart...")
        self.walmart_auth = WalmartAuthenticator(self.browser)
        page = self.walmart_auth.authenticate()
        logger.success("Walmart authentication successful")
        return page

    def _close_walmart(self) -> None:
        """Close Walmart page and context to save resources."""
        try:
            if self.walmart_auth:
                self.walmart_auth.close()
                self.walmart_auth = None

            self.walmart_page = None
            logger.info("Walmart page closed successfully")
        except Exception as e:
            logger.warning(f"Error closing Walmart page: {e}")

    def _remove_items_from_file(self, file_path: str, items_to_remove: list) -> None:
        """Remove successfully added items from the shopping list file.

        Args:
            file_path: Path to the shopping list file
            items_to_remove: List of item dicts that were successfully added
        """
        try:
            # Read existing file
            with open(file_path, 'r') as f:
                lines = f.readlines()

            # Build set of item names to remove
            names_to_remove = {item['name'].lower() for item in items_to_remove}

            # Filter out lines that match removed items
            remaining_lines = []
            for line in lines:
                # Skip if this line contains an item name we're removing
                line_lower = line.lower()
                if not any(name in line_lower for name in names_to_remove):
                    remaining_lines.append(line)

            # Write back the remaining items
            with open(file_path, 'w') as f:
                f.writelines(remaining_lines)

            logger.info(f"Removed {len(items_to_remove)} items from {file_path}")

        except Exception as e:
            logger.error(f"Error updating shopping list file: {e}")
            raise

    def _save_items_to_file(self, items: list) -> str:
        """Save scraped items to a .txt file.

        Args:
            items: List of items from Amazon

        Returns:
            Path to saved file
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"shopping_list_{timestamp}.txt"
        filepath = Path(filename)

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"Amazon Shopping List - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")

                for i, item in enumerate(items, 1):
                    f.write(f"{i}. {item['name']}\n")
                    f.write(f"   Quantity: {item['quantity']}\n")
                    if item.get('raw_text'):
                        f.write(f"   Raw: {item['raw_text']}\n")
                    f.write("\n")

                f.write("=" * 60 + "\n")
                f.write(f"Total items: {len(items)}\n")

            logger.success(f"Saved {len(items)} items to {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"Failed to save items to file: {e}")
            return ""

    def cleanup(self) -> None:
        """Cleanup resources."""
        logger.info("Cleaning up resources...")

        try:
            # Don't close pages in scheduled mode (they're reused)
            # Only close contexts
            if self.amazon_auth:
                self.amazon_auth.close()
            if self.walmart_auth:
                self.walmart_auth.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()

            # Reset page references
            self.amazon_page = None
            self.walmart_page = None

            logger.info("Cleanup complete")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Amazon to Walmart shopping list automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/main.py                    # Run on schedule (random 3-5 min intervals)
  python src/main.py --once             # Run once and exit
  python src/main.py --once --headed    # Run once with visible browser
        """
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (instead of running on schedule)"
    )

    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show browser window (non-headless mode)"
    )

    args = parser.parse_args()

    # Determine headless setting (None = use config, False = show browser, True = hide browser)
    headless = None if not args.headed else False

    # Initialize automation
    automation = AmazonWalmartAutomation(headless=headless)

    # Run once or on schedule
    if args.once:
        automation.run_once()
    else:
        automation.run_scheduled()


if __name__ == "__main__":
    main()
