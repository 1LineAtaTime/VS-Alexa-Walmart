"""Home Assistant notification integration for Alexa announcements."""

import requests
from typing import List, Dict, Any
from loguru import logger

from ..config import settings


class HomeAssistantNotifier:
    """Send notifications via Home Assistant Alexa Media Player."""

    def __init__(self):
        """Initialize the Home Assistant notifier."""
        self.ha_url = settings.home_assistant_url
        self.ha_token = settings.home_assistant_token
        self.alexa_entity = settings.home_assistant_alexa_entity

        # Validate configuration
        self.enabled = bool(self.ha_url and self.ha_token and self.alexa_entity)

        if not self.enabled:
            logger.warning("Home Assistant notifications disabled - missing configuration")
            logger.info("To enable: Set HOME_ASSISTANT_URL, HOME_ASSISTANT_TOKEN, and HOME_ASSISTANT_ALEXA_ENTITY in credentials.py")

    def notify_failed_items(self, failed_items: List[Dict[str, Any]]) -> bool:
        """Send notification about items that failed to add to cart.

        Args:
            failed_items: List of item dictionaries that failed to add

        Returns:
            True if notification was sent successfully
        """
        if not self.enabled:
            logger.debug("Home Assistant notifications not configured, skipping")
            return False

        if not failed_items:
            logger.debug("No failed items to notify about")
            return False

        try:
            # Build the notification message
            item_count = len(failed_items)

            if item_count == 1:
                message = f"Attention. I could not add {failed_items[0]['name']} to the Walmart cart"
            else:
                # List item names
                item_names = [item['name'] for item in failed_items]
                if item_count <= 3:
                    # List all items if 3 or fewer
                    items_text = ", ".join(item_names[:-1]) + f" and {item_names[-1]}"
                    message = f"Attention. I could not add {items_text} to the Walmart cart"
                else:
                    # Just say the count if more than 3 items
                    message = f"Attention. I could not add {item_count} items to the Walmart cart"

            logger.info(f"Sending notification to {self.alexa_entity}: {message}")

            # Call Home Assistant TTS service
            success = self._send_tts_announcement(message)

            if success:
                logger.success("Notification sent successfully via Home Assistant")
            else:
                logger.warning("Failed to send notification via Home Assistant")

            return success

        except Exception as e:
            logger.error(f"Error sending Home Assistant notification: {e}")
            return False

    def _send_tts_announcement(self, message: str) -> bool:
        """Send TTS announcement via Home Assistant REST API.

        Args:
            message: Message to announce

        Returns:
            True if request was successful
        """
        try:
            # Build the API endpoint
            url = f"{self.ha_url.rstrip('/')}/api/services/notify/alexa_media"

            headers = {
                "Authorization": f"Bearer {self.ha_token}",
                "Content-Type": "application/json"
            }

            # Build the service call data
            data = {
                "target": self.alexa_entity,
                "data": {
                    "type": "tts"
                },
                "message": message
            }

            # Send the request
            response = requests.post(url, headers=headers, json=data, timeout=10)

            if response.status_code in [200, 201]:
                logger.debug(f"Home Assistant API call successful: {response.status_code}")
                return True
            else:
                logger.warning(f"Home Assistant API returned status {response.status_code}: {response.text}")
                return False

        except requests.exceptions.Timeout:
            logger.error("Home Assistant API request timed out")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Could not connect to Home Assistant: {e}")
            logger.info("Make sure HOME_ASSISTANT_URL is correct and Home Assistant is accessible")
            return False
        except Exception as e:
            logger.error(f"Error calling Home Assistant API: {e}")
            return False

    def test_connection(self) -> bool:
        """Test connection to Home Assistant.

        Returns:
            True if connection is working
        """
        if not self.enabled:
            logger.warning("Home Assistant not configured")
            return False

        try:
            url = f"{self.ha_url.rstrip('/')}/api/"
            headers = {"Authorization": f"Bearer {self.ha_token}"}

            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                logger.success("Successfully connected to Home Assistant")
                return True
            else:
                logger.warning(f"Home Assistant API returned status {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Failed to connect to Home Assistant: {e}")
            return False
