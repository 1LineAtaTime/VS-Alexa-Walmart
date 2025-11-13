"""Fuzzy matching logic for finding best item match."""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from rapidfuzz import fuzz, process
from loguru import logger


@dataclass
class MatchResult:
    """Result of item matching."""

    item_id: str
    item_name: str
    price: float
    score: int
    in_stock: bool
    frequently_bought: bool
    product_url: str
    image_url: Optional[str] = None
    my_items_page: Optional[int] = None  # Which My Items page this was found on


class ItemMatcher:
    """Intelligent item matcher using fuzzy string matching."""

    def __init__(
        self,
        min_score: int = 70,
        prefer_frequent: bool = True,
        prefer_in_stock: bool = True,
    ):
        """Initialize item matcher.

        Args:
            min_score: Minimum fuzzy match score (0-100)
            prefer_frequent: Boost score for frequently bought items
            prefer_in_stock: Boost score for in-stock items
        """
        self.min_score = min_score
        self.prefer_frequent = prefer_frequent
        self.prefer_in_stock = prefer_in_stock

    def find_best_match(
        self,
        query: str,
        items: List[Dict[str, Any]],
        my_items: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[MatchResult]:
        """Find the best matching item from search results.

        Args:
            query: User's search query (e.g., "2% milk")
            items: List of items from search results
            my_items: Optional list of previously purchased items

        Returns:
            MatchResult if a good match is found, None otherwise
        """
        if not items:
            logger.warning("No items to match")
            return None

        logger.info(f"Matching query '{query}' against {len(items)} items")

        # Create a mapping of item names to items for quick lookup
        item_map = {item["name"]: item for item in items if item.get("name")}

        # First, check if query matches any previously purchased items
        if my_items:
            my_items_map = {item["name"]: item for item in my_items if item.get("name")}
            my_match = self._find_in_my_items(query, my_items_map, item_map)
            if my_match:
                logger.info("Found match in previously purchased items")
                return my_match

        # Perform fuzzy matching on all items
        scored_items = []

        for item in items:
            name = item.get("name", "")
            if not name:
                continue

            # Calculate base similarity score
            score = fuzz.token_sort_ratio(query.lower(), name.lower())

            # Apply boosting based on preferences
            boosted_score = score

            if self.prefer_frequent and item.get("frequently_bought"):
                boosted_score += 5
                logger.debug(f"Boosting frequently bought item: {name}")

            if self.prefer_in_stock and item.get("in_stock"):
                boosted_score += 3
            elif not item.get("in_stock"):
                # Penalize out of stock items
                boosted_score -= 10

            scored_items.append({
                "item": item,
                "score": score,
                "boosted_score": boosted_score,
            })

        # Sort by boosted score
        scored_items.sort(key=lambda x: x["boosted_score"], reverse=True)

        # Get best match
        if scored_items and scored_items[0]["score"] >= self.min_score:
            best = scored_items[0]
            item = best["item"]

            logger.success(
                f"Best match: '{item['name']}' "
                f"(score: {best['score']}, boosted: {best['boosted_score']})"
            )

            return MatchResult(
                item_id=item["id"],
                item_name=item["name"],
                price=item.get("price", 0.0),
                score=best["score"],
                in_stock=item.get("in_stock", False),
                frequently_bought=item.get("frequently_bought", False),
                product_url=item.get("product_url", ""),
                image_url=item.get("image"),
                my_items_page=item.get("my_items_page"),  # Preserve page number if from My Items
            )

        logger.warning(
            f"No match found above threshold {self.min_score}. "
            f"Best score: {scored_items[0]['score'] if scored_items else 0}"
        )
        return None

    def _find_in_my_items(
        self,
        query: str,
        my_items_map: Dict[str, Dict],
        search_items_map: Dict[str, Dict],
    ) -> Optional[MatchResult]:
        """Check if query matches any previously purchased items.

        Args:
            query: Search query
            my_items_map: Map of item names to my items
            search_items_map: Map of item names to search results

        Returns:
            MatchResult if found in both my items and search results
        """
        # Use fuzzy matching on previously purchased items
        match = process.extractOne(
            query.lower(),
            [name.lower() for name in my_items_map.keys()],
            scorer=fuzz.token_sort_ratio,
            score_cutoff=self.min_score,
        )

        if match:
            matched_name = match[0]
            score = match[1]

            # Find the original item name (with correct casing)
            original_name = None
            for name in my_items_map.keys():
                if name.lower() == matched_name:
                    original_name = name
                    break

            # Check if this item is also in search results
            if original_name and original_name in search_items_map:
                item = search_items_map[original_name]

                logger.info(f"Found in My Items: '{original_name}' (score: {score})")

                return MatchResult(
                    item_id=item["id"],
                    item_name=item["name"],
                    price=item.get("price", 0.0),
                    score=score + 10,  # Boost for being in my items
                    in_stock=item.get("in_stock", False),
                    frequently_bought=True,  # From my items
                    product_url=item.get("product_url", ""),
                    image_url=item.get("image"),
                    my_items_page=item.get("my_items_page"),  # Preserve page number
                )

        return None

    def get_top_matches(
        self,
        query: str,
        items: List[Dict[str, Any]],
        limit: int = 5,
    ) -> List[MatchResult]:
        """Get top N matching items.

        Args:
            query: Search query
            items: List of items
            limit: Number of results to return

        Returns:
            List of top MatchResults
        """
        if not items:
            return []

        results = []

        for item in items:
            name = item.get("name", "")
            if not name:
                continue

            score = fuzz.token_sort_ratio(query.lower(), name.lower())

            if score >= self.min_score:
                results.append(
                    MatchResult(
                        item_id=item["id"],
                        item_name=item["name"],
                        price=item.get("price", 0.0),
                        score=score,
                        in_stock=item.get("in_stock", False),
                        frequently_bought=item.get("frequently_bought", False),
                        product_url=item.get("product_url", ""),
                        image_url=item.get("image"),
                    )
                )

        # Sort by score and return top N
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]
