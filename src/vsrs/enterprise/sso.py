"""Single Sign-On (SSO) integration for VSRS.

Supports SAML 2.0 and OpenID Connect (OIDC) protocols for enterprise
authentication. Provides provider configuration, token validation,
session management, and automatic user provisioning.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from vsrs.core.logging import get_logger
from vsrs.enterprise.auth import User

logger = get_logger("enterprise.sso")


class SSOProtocol(str, Enum):
    """Supported SSO protocols."""

    saml = "saml"
    oidc = "oidc"


class SSOProviderStatus(str, Enum):
    """Status of an SSO provider."""

    active = "active"
    disabled = "disabled"


@dataclass
class SAMLProvider:
    """SAML 2.0 identity provider configuration.

    Attributes:
        id: Unique provider identifier.
        name: Display name.
        entity_id: IdP entity ID.
        sso_url: Single Sign-On service URL.
        slo_url: Single Logout service URL.
        x509_cert: X.509 certificate for signature verification.
        audience: Expected audience (SP entity ID).
        attribute_mapping: Maps SAML attributes to user fields.
    """

    id: str
    name: str
    entity_id: str
    sso_url: str
    slo_url: str = ""
    x509_cert: str = ""
    audience: str = "vsrs"
    attribute_mapping: dict[str, str] = field(default_factory=lambda: {
        "email": "email",
        "name": "name",
        "role": "role",
    })

    @property
    def protocol(self) -> SSOProtocol:
        return SSOProtocol.saml

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "protocol": self.protocol.value,
            "entity_id": self.entity_id,
            "sso_url": self.sso_url,
            "slo_url": self.slo_url,
            "x509_cert": self.x509_cert[:20] + "..." if len(self.x509_cert) > 20 else self.x509_cert,
            "audience": self.audience,
            "attribute_mapping": self.attribute_mapping,
        }


@dataclass
class OIDCProvider:
    """OpenID Connect provider configuration.

    Attributes:
        id: Unique provider identifier.
        name: Display name.
        issuer_url: OIDC issuer URL (e.g., https://accounts.google.com).
        client_id: OAuth/OIDC client ID.
        client_secret: Client secret (stored encrypted in production).
        scopes: Requested OIDC scopes.
        userinfo_url: UserInfo endpoint URL.
        token_url: Token endpoint URL.
        authorize_url: Authorization endpoint URL.
    """

    id: str
    name: str
    issuer_url: str
    client_id: str
    client_secret: str = ""
    scopes: list[str] = field(default_factory=lambda: ["openid", "email", "profile"])
    userinfo_url: str = ""
    token_url: str = ""
    authorize_url: str = ""

    @property
    def protocol(self) -> SSOProtocol:
        return SSOProtocol.oidc

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "protocol": self.protocol.value,
            "issuer_url": self.issuer_url,
            "client_id": self.client_id,
            "client_secret": "***" if self.client_secret else "",
            "scopes": self.scopes,
            "userinfo_url": self.userinfo_url,
            "token_url": self.token_url,
            "authorize_url": self.authorize_url,
        }


@dataclass
class SSOSession:
    """An SSO authenticated session.

    Attributes:
        id: Session identifier.
        user_id: ID of the authenticated user.
        provider_id: SSO provider used.
        protocol: Protocol used (saml or oidc).
        created_at: When the session was created.
        expires_at: When the session expires.
        token: Session token (for cookie/header).
        refresh_token: OIDC refresh token (if applicable).
        attributes: Raw attributes from the IdP.
    """

    id: str
    user_id: str
    provider_id: str
    protocol: SSOProtocol
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=8))
    token: str = ""
    refresh_token: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_expired

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "provider_id": self.provider_id,
            "protocol": self.protocol.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "is_valid": self.is_valid,
            "attributes": self.attributes,
        }


class SSOError(Exception):
    """Base SSO error."""

    pass


class SSOProviderNotFoundError(SSOError):
    """Raised when an SSO provider is not found."""

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        super().__init__(f"SSO provider not found: {provider_id}")


class SSOAuthenticationError(SSOError):
    """Raised when SSO authentication fails."""

    pass


class SSOTokenExpiredError(SSOError):
    """Raised when an SSO token has expired."""

    pass


def _generate_session_token() -> str:
    """Generate a cryptographically secure session token."""
    return f"sso_{secrets.token_urlsafe(48)}"


def _decode_base64_url(data: str) -> bytes:
    """Decode a base64url-encoded string (no padding)."""
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode a JWT payload without verification (for inspection only).

    In production, always verify the JWT signature using the provider's
    public keys before trusting the payload.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise SSOAuthenticationError("Invalid JWT format")
    try:
        payload_bytes = _decode_base64_url(parts[1])
        return json.loads(payload_bytes)
    except (json.JSONDecodeError, ValueError) as e:
        raise SSOAuthenticationError(f"Failed to decode JWT payload: {e}")


class SSOManager:
    """Manages SSO providers, authentication flows, and sessions.

    Supports both SAML 2.0 and OIDC providers. Handles:
    - Provider registration and configuration
    - Authentication flow initiation (generate redirect URLs)
    - Token/callback validation
    - Session creation and management
    - Automatic user provisioning from IdP attributes
    """

    def __init__(self) -> None:
        self._saml_providers: dict[str, SAMLProvider] = {}
        self._oidc_providers: dict[str, OIDCProvider] = {}
        self._sessions: dict[str, SSOSession] = {}
        self._sessions_by_token: dict[str, SSOSession] = {}
        self._users: dict[str, User] = {}
        self._user_by_provider: dict[str, str] = {}  # "provider_id:external_id" -> user_id

    # --- Provider management ---

    def register_saml_provider(self, provider: SAMLProvider) -> SAMLProvider:
        """Register a SAML identity provider."""
        self._saml_providers[provider.id] = provider
        logger.info(f"SAML provider registered: {provider.id} ({provider.name})")
        return provider

    def register_oidc_provider(self, provider: OIDCProvider) -> OIDCProvider:
        """Register an OIDC identity provider."""
        self._oidc_providers[provider.id] = provider
        logger.info(f"OIDC provider registered: {provider.id} ({provider.name})")
        return provider

    def get_saml_provider(self, provider_id: str) -> SAMLProvider:
        if provider_id not in self._saml_providers:
            raise SSOProviderNotFoundError(provider_id)
        return self._saml_providers[provider_id]

    def get_oidc_provider(self, provider_id: str) -> OIDCProvider:
        if provider_id not in self._oidc_providers:
            raise SSOProviderNotFoundError(provider_id)
        return self._oidc_providers[provider_id]

    def list_providers(self) -> list[dict[str, Any]]:
        """List all registered SSO providers."""
        providers = []
        for p in self._saml_providers.values():
            providers.append(p.to_dict())
        for p in self._oidc_providers.values():
            providers.append(p.to_dict())
        return providers

    def remove_provider(self, provider_id: str) -> None:
        """Remove an SSO provider."""
        self._saml_providers.pop(provider_id, None)
        self._oidc_providers.pop(provider_id, None)
        logger.info(f"SSO provider removed: {provider_id}")

    # --- OIDC authentication flow ---

    def get_oidc_authorize_url(
        self,
        provider_id: str,
        redirect_uri: str,
        state: str | None = None,
    ) -> str:
        """Build the OIDC authorization redirect URL.

        Args:
            provider_id: The OIDC provider ID.
            redirect_uri: Where to redirect after authentication.
            state: Optional state parameter for CSRF protection.

        Returns:
            Full authorization URL to redirect the user to.
        """
        provider = self.get_oidc_provider(provider_id)
        if not provider.authorize_url:
            raise SSOError(f"OIDC provider '{provider_id}' has no authorize_url configured")

        state = state or secrets.token_urlsafe(16)
        params = {
            "response_type": "code",
            "client_id": provider.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(provider.scopes),
            "state": state,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{provider.authorize_url}?{query}"

    def validate_oidc_token(self, provider_id: str, token: str) -> dict[str, Any]:
        """Validate an OIDC ID token or access token.

        Decodes the JWT payload and checks expiration. In production,
        this should also verify the JWT signature using the provider's
        public keys.

        Args:
            provider_id: The OIDC provider ID.
            token: The JWT token to validate.

        Returns:
            Decoded token claims.

        Raises:
            SSOAuthenticationError: If the token is invalid.
            SSOTokenExpiredError: If the token has expired.
        """
        provider = self.get_oidc_provider(provider_id)
        claims = _decode_jwt_payload(token)

        # Check expiration
        exp = claims.get("exp")
        if exp is not None:
            if time.time() > exp:
                raise SSOTokenExpiredError(f"Token expired at {exp}")

        # Check issuer
        iss = claims.get("iss")
        if iss and provider.issuer_url and iss != provider.issuer_url:
            logger.warning(f"Issuer mismatch: expected {provider.issuer_url}, got {iss}")

        # Check audience
        aud = claims.get("aud")
        if aud and provider.client_id and aud != provider.client_id:
            logger.warning(f"Audience mismatch: expected {provider.client_id}, got {aud}")

        return claims

    def authenticate_oidc(
        self,
        provider_id: str,
        id_token: str,
        userinfo: dict[str, Any] | None = None,
    ) -> SSOSession:
        """Authenticate a user via OIDC.

        Args:
            provider_id: The OIDC provider ID.
            id_token: The OIDC ID token (JWT).
            userinfo: Optional userinfo response from the provider.

        Returns:
            An SSO session for the authenticated user.
        """
        provider = self.get_oidc_provider(provider_id)
        claims = self.validate_oidc_token(provider_id, id_token)

        # Extract user info from claims + userinfo
        external_id = claims.get("sub", "")
        email = (userinfo or {}).get("email") or claims.get("email", "")
        name = (userinfo or {}).get("name") or claims.get("name", "")
        username = email.split("@")[0] if email else external_id

        # Provision or find user
        user = self._provision_user(
            provider_id=provider_id,
            external_id=external_id,
            username=username,
            email=email,
            name=name,
            attributes={**claims, **(userinfo or {})},
        )

        # Create session
        session = self._create_session(
            user_id=user.id,
            provider_id=provider_id,
            protocol=SSOProtocol.oidc,
            attributes={**claims, **(userinfo or {})},
        )

        logger.info(f"OIDC authentication successful: user={user.id}, provider={provider_id}")
        return session

    # --- SAML authentication flow ---

    def get_saml_redirect_url(
        self,
        provider_id: str,
        relay_state: str | None = None,
    ) -> str:
        """Build the SAML redirect URL (SAMLRequest parameter).

        In a real implementation, this would generate a signed SAML
        AuthnRequest XML, base64-encode it, and URL-encode it.

        Args:
            provider_id: The SAML provider ID.
            relay_state: Optional relay state for the request.

        Returns:
            URL to redirect the user to.
        """
        provider = self.get_saml_provider(provider_id)
        # Simplified: in production, generate proper SAML AuthnRequest
        authn_request = f"<samlp:AuthnRequest xmlns:samlp='urn:oasis:names:tc:SAML:2.0:protocol' AssertionConsumerServiceURL='{provider.audience}' ID='{secrets.token_hex(16)}' Version='2.0'/>"
        encoded = base64.b64encode(authn_request.encode()).decode()

        url = f"{provider.sso_url}?SAMLRequest={encoded}"
        if relay_state:
            url += f"&RelayState={relay_state}"
        return url

    def validate_saml_response(
        self,
        provider_id: str,
        saml_response: str,
    ) -> dict[str, Any]:
        """Validate a SAML response from the IdP.

        Decodes the base64-encoded SAML response and extracts attributes.
        In production, this should verify the XML signature using the
        provider's X.509 certificate.

        Args:
            provider_id: The SAML provider ID.
            saml_response: Base64-encoded SAML response.

        Returns:
            Extracted SAML attributes.

        Raises:
            SSOAuthenticationError: If the response is invalid.
        """
        provider = self.get_saml_provider(provider_id)

        try:
            xml_bytes = base64.b64decode(saml_response)
            xml_str = xml_bytes.decode("utf-8")
        except Exception as e:
            raise SSOAuthenticationError(f"Failed to decode SAML response: {e}")

        # Simplified attribute extraction (production: use xmlsec or lxml)
        attributes: dict[str, Any] = {}

        # Extract NameID
        if "NameID" in xml_str:
            start = xml_str.find("<saml:NameID>") + len("<saml:NameID>")
            end = xml_str.find("</saml:NameID>")
            if start > len("<saml:NameID>") and end > start:
                attributes["name_id"] = xml_str[start:end].strip()

        # Extract email attribute
        if "EmailAddress" in xml_str:
            start = xml_str.find("EmailAddress") + len("EmailAddress")
            end = xml_str.find("<", start)
            if end > start:
                attributes["email"] = xml_str[start:end].strip().lstrip(">").strip()

        # Extract name attribute
        if " saml:AttributeValue" in xml_str:
            # Very simplified extraction
            pass

        # Check audience
        if provider.audience and provider.audience not in xml_str:
            logger.warning(f"Audience mismatch in SAML response for provider {provider_id}")

        attributes["_raw_xml"] = xml_str
        return attributes

    def authenticate_saml(
        self,
        provider_id: str,
        saml_response: str,
    ) -> SSOSession:
        """Authenticate a user via SAML.

        Args:
            provider_id: The SAML provider ID.
            saml_response: Base64-encoded SAML response from the IdP.

        Returns:
            An SSO session for the authenticated user.
        """
        provider = self.get_saml_provider(provider_id)
        attributes = self.validate_saml_response(provider_id, saml_response)

        external_id = attributes.get("name_id", "")
        email = attributes.get("email", "")
        name = attributes.get("name", "")
        username = email.split("@")[0] if email else external_id

        # Map attributes using provider config
        mapping = provider.attribute_mapping
        mapped_attrs: dict[str, Any] = {}
        for saml_attr, user_field in mapping.items():
            if saml_attr in attributes:
                mapped_attrs[user_field] = attributes[saml_attr]

        # Provision or find user
        user = self._provision_user(
            provider_id=provider_id,
            external_id=external_id,
            username=username,
            email=email,
            name=name,
            attributes=mapped_attrs,
        )

        # Create session
        session = self._create_session(
            user_id=user.id,
            provider_id=provider_id,
            protocol=SSOProtocol.saml,
            attributes=attributes,
        )

        logger.info(f"SAML authentication successful: user={user.id}, provider={provider_id}")
        return session

    # --- Session management ---

    def get_session(self, token: str) -> SSOSession | None:
        """Get a session by its token."""
        session = self._sessions_by_token.get(token)
        if session is None:
            return None
        if session.is_expired:
            self.logout(token)
            return None
        return session

    def get_session_by_id(self, session_id: str) -> SSOSession | None:
        """Get a session by its ID."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired:
            self.logout(session.token)
            return None
        return session

    def logout(self, token: str) -> bool:
        """Logout a session by token.

        Returns:
            True if the session was found and removed, False otherwise.
        """
        session = self._sessions_by_token.pop(token, None)
        if session is None:
            return False
        self._sessions.pop(session.id, None)
        logger.info(f"SSO session ended: {session.id}")
        return True

    def refresh_session(self, session_id: str, extend_hours: int = 8) -> SSOSession:
        """Extend a session's expiration time.

        Args:
            session_id: The session ID to refresh.
            extend_hours: Hours to extend the session by.

        Returns:
            The refreshed session.

        Raises:
            SSOError: If the session is not found.
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise SSOError(f"Session not found: {session_id}")
        session.expires_at = datetime.now(timezone.utc) + timedelta(hours=extend_hours)
        logger.debug(f"SSO session refreshed: {session_id}")
        return session

    def cleanup_expired_sessions(self) -> int:
        """Remove all expired sessions.

        Returns:
            Number of sessions removed.
        """
        expired_tokens = [
            s.token for s in self._sessions.values() if s.is_expired
        ]
        for token in expired_tokens:
            self.logout(token)
        if expired_tokens:
            logger.info(f"Cleaned up {len(expired_tokens)} expired SSO sessions")
        return len(expired_tokens)

    def list_active_sessions(self) -> list[SSOSession]:
        """List all active (non-expired) sessions."""
        return [s for s in self._sessions.values() if s.is_valid]

    # --- User provisioning ---

    def get_user(self, user_id: str) -> User | None:
        """Get a provisioned user by ID."""
        return self._users.get(user_id)

    def list_users(self) -> list[User]:
        """List all provisioned users."""
        return list(self._users.values())

    def _provision_user(
        self,
        provider_id: str,
        external_id: str,
        username: str,
        email: str,
        name: str,
        attributes: dict[str, Any],
    ) -> User:
        """Find or create a user from SSO attributes."""
        lookup_key = f"{provider_id}:{external_id}"

        if lookup_key in self._user_by_provider:
            user_id = self._user_by_provider[lookup_key]
            user = self._users[user_id]
            # Update user info from latest SSO attributes
            user.email = email or user.email
            if "role" in attributes:
                user.role = attributes["role"]
            user.metadata["last_sso_login"] = datetime.now(timezone.utc).isoformat()
            user.metadata["sso_attributes"] = attributes
            return user

        # Create new user
        user_id = f"u_{secrets.token_hex(8)}"
        user = User(
            id=user_id,
            username=username or f"user_{user_id[:8]}",
            email=email,
            role=attributes.get("role", "viewer"),
            metadata={
                "sso_provider": provider_id,
                "external_id": external_id,
                "name": name,
                "sso_attributes": attributes,
                "provisioned_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        self._users[user_id] = user
        self._user_by_provider[lookup_key] = user_id
        logger.info(f"User provisioned via SSO: {user_id} (provider: {provider_id})")
        return user

    # --- Internal helpers ---

    def _create_session(
        self,
        user_id: str,
        provider_id: str,
        protocol: SSOProtocol,
        attributes: dict[str, Any],
    ) -> SSOSession:
        """Create a new SSO session."""
        session_id = f"sess_{secrets.token_hex(12)}"
        token = _generate_session_token()

        session = SSOSession(
            id=session_id,
            user_id=user_id,
            provider_id=provider_id,
            protocol=protocol,
            token=token,
            attributes=attributes,
        )
        self._sessions[session_id] = session
        self._sessions_by_token[token] = session
        return session

    # --- Stats ---

    @property
    def session_count(self) -> int:
        """Number of active sessions."""
        return len([s for s in self._sessions.values() if s.is_valid])

    @property
    def user_count(self) -> int:
        """Number of provisioned users."""
        return len(self._users)

    @property
    def provider_count(self) -> int:
        """Total number of registered providers."""
        return len(self._saml_providers) + len(self._oidc_providers)
