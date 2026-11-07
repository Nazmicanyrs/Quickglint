"""Quickglint Favorites Package."""

from app.favorites.manager import FavoritesManager, FavoritesSignals
from app.favorites.models import FavoriteItem

__all__ = [
    "FavoriteItem",
    "FavoritesManager",
    "FavoritesSignals",
]

