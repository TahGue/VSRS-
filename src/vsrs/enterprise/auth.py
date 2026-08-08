"""Authentication models and API key management.

Provides User, APIKey, AuthContext data structures and an APIKeyManager
for creating, validating, and revoking API keys.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from vsrs.core.logging import get_logger

logger = get_logger("enterprise.auth")


@dataclass
class User:
    """A user in the system.

    Attributes:
        id: Unique user identifier.
        username: Login name.
        email: Email address.
        role: Role name (e.g. "admin", "developer", "viewer").
        active: Whether the user is active.
        created_at: When the user was created.
        metadata: Additional user metadata.
    """

    id: str
    username: str
    email: str = ""
    role: str = "viewer"
    active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "active": self.active,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class APIKey:
    """An API key for programmatic access.

    Attributes:
        id: Unique key identifier.
        key_hash: SHA-256 hash of the key (never store the raw key).
        user_id: ID of the user who owns this key.
        name: Human-readable name for the key.
        scopes: List of permission scopes.
        created_at: When the key was created.
        last_used: When the key was last used.
        expires_at: When the key expires (None = never).
        revoked: Whether the key has been revoked.
    """

    id: str
    key_hash: str
    user_id: str
    name: str = ""
    scopes: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used: datetime | None = None
    expires_at: datetime | None = None
    revoked: bool = False

    @property
    def is_valid(self) -> bool:
        """Check if the key is still valid (not revoked, not expired)."""
        if self.revoked:
            return False
        if self.expires_at is not None:
            if datetime.now(timezone.utc) > self.expires_at:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key_hash": self.key_hash,
            "user_id": self.user_id,
            "name": self.name,
            "scopes": self.scopes,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked": self.revoked,
            "is_valid": self.is_valid,
        }


@dataclass
class AuthContext:
    """Authentication context for a request.

    Carries user and API key information through the request lifecycle.

    Attributes:
        user: The authenticated user.
        api_key: The API key used (if any).
        authenticated: Whether the request is authenticated.
    """

    user: User | None = None
    api_key: APIKey | None = None
    authenticated: bool = False

    @property
    def user_id(self) -> str | None:
        return self.user.id if self.user else None

    @property
    def role(self) -> str | None:
        return self.user.role if self.user else None


def _hash_key(raw_key: str) -> str:
    """Hash an API key for secure storage."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _generate_key() -> str:
    """Generate a cryptographically secure API key."""
    return f"vsrs_{secrets.token_urlsafe(32)}"


class APIKeyManager:
    """Manages API key lifecycle: creation, validation, revocation.

    Stores keys as hashes (never raw keys). Validates incoming keys
    by comparing hashes.
    """

    def __init__(self) -> None:
        self._keys: dict[str, APIKey] = {}  # id -> APIKey
        self._hash_index: dict[str, str] = {}  # key_hash -> key_id

    def create_key(
        self,
        user_id: str,
        name: str = "",
        scopes: list[str] | None = None,
        expires_at: datetime | None = None,
    ) -> tuple[str, APIKey]:
        """Create a new API key.

        Args:
            user_id: ID of the user who owns this key.
            name: Human-readable name.
            scopes: Permission scopes.
            expires_at: Expiration time (None = never).

        Returns:
            Tuple of (raw_key, APIKey). The raw_key is only returned once.
        """
        raw_key = _generate_key()
        key_hash = _hash_key(raw_key)
        key_id = f"key_{secrets.token_hex(8)}"

        api_key = APIKey(
            id=key_id,
            key_hash=key_hash,
            user_id=user_id,
            name=name,
            scopes=scopes or [],
            expires_at=expires_at,
        )

        self._keys[key_id] = api_key
        self._hash_index[key_hash] = key_id
        logger.info(f"Created API key {key_id} for user {user_id} (name={name})")
        return raw_key, api_key

    def validate(self, raw_key: str) -> APIKey | None:
        """Validate an API key and return the key if valid.

        Args:
            raw_key: The raw API key to validate.

        Returns:
            The APIKey if valid, None if invalid/expired/revoked.
        """
        key_hash = _hash_key(raw_key)
        key_id = self._hash_index.get(key_hash)
        if key_id is None:
            return None

        api_key = self._keys.get(key_id)
        if api_key is None:
            return None

        if not api_key.is_valid:
            return None

        # Update last used
        api_key.last_used = datetime.now(timezone.utc)
        return api_key

    def revoke(self, key_id: str) -> bool:
        """Revoke an API key.

        Returns:
            True if revoked, False if not found.
        """
        api_key = self._keys.get(key_id)
        if api_key is None:
            return False
        api_key.revoked = True
        logger.info(f"Revoked API key {key_id}")
        return True

    def get(self, key_id: str) -> APIKey | None:
        """Get an API key by ID."""
        return self._keys.get(key_id)

    def list_keys(self, user_id: str | None = None) -> list[APIKey]:
        """List API keys, optionally filtered by user."""
        keys = list(self._keys.values())
        if user_id is not None:
            keys = [k for k in keys if k.user_id == user_id]
        return keys

    def count(self) -> int:
        """Get total number of keys."""
        return len(self._keys)

    def clear(self) -> None:
        """Remove all keys."""
        self._keys.clear()
        self._hash_index.clear()
