"""Tests for Phase 26: SSO integration (SAML, OIDC).

Tests SSO provider models, SSOManager authentication flows,
session management, user provisioning, and error handling.
"""

import base64
import json
import time
import pytest
from datetime import datetime, timedelta, timezone

from vsrs.enterprise.sso import (
    OIDCProvider,
    SAMLProvider,
    SSOAuthenticationError,
    SSOError,
    SSOManager,
    SSOProtocol,
    SSOProviderNotFoundError,
    SSOSession,
    SSOTokenExpiredError,
)
from vsrs.enterprise.auth import User


# --- Helper functions ---

def _make_jwt(payload: dict, header: dict | None = None) -> str:
    """Create a minimal unsigned JWT for testing."""
    h = header or {"alg": "none", "typ": "JWT"}
    h_b64 = base64.urlsafe_b64encode(json.dumps(h).encode()).rstrip(b"=").decode()
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{h_b64}.{p_b64}.signature"


def _make_saml_response(name_id: str = "user@example.com", email: str = "user@example.com") -> str:
    """Create a minimal base64-encoded SAML response for testing."""
    xml = f"""<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
  <saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    <saml:Subject>
      <saml:NameID>{name_id}</saml:NameID>
    </saml:Subject>
    <saml:AttributeStatement>
      <saml:Attribute Name="EmailAddress">
        <saml:AttributeValue>{email}</saml:AttributeValue>
      </saml:Attribute>
    </saml:AttributeStatement>
    <saml:Audience>vsrs</saml:Audience>
  </saml:Assertion>
</samlp:Response>"""
    return base64.b64encode(xml.encode()).decode()


# --- SAMLProvider tests ---

class TestSAMLProvider:
    def test_create(self):
        p = SAMLProvider(
            id="okta",
            name="Okta",
            entity_id="https://okta.com/entity",
            sso_url="https://okta.com/sso",
        )
        assert p.id == "okta"
        assert p.name == "Okta"
        assert p.protocol == SSOProtocol.saml

    def test_to_dict(self):
        p = SAMLProvider(id="okta", name="Okta", entity_id="eid", sso_url="url")
        d = p.to_dict()
        assert d["id"] == "okta"
        assert d["protocol"] == "saml"
        assert d["entity_id"] == "eid"

    def test_default_attribute_mapping(self):
        p = SAMLProvider(id="okta", name="Okta", entity_id="eid", sso_url="url")
        assert "email" in p.attribute_mapping
        assert "name" in p.attribute_mapping
        assert "role" in p.attribute_mapping

    def test_custom_attribute_mapping(self):
        p = SAMLProvider(
            id="okta", name="Okta", entity_id="eid", sso_url="url",
            attribute_mapping={"http://schemas/email": "email"},
        )
        assert p.attribute_mapping == {"http://schemas/email": "email"}


# --- OIDCProvider tests ---

class TestOIDCProvider:
    def test_create(self):
        p = OIDCProvider(
            id="google",
            name="Google",
            issuer_url="https://accounts.google.com",
            client_id="client123",
        )
        assert p.id == "google"
        assert p.protocol == SSOProtocol.oidc

    def test_to_dict(self):
        p = OIDCProvider(
            id="google", name="Google", issuer_url="https://accounts.google.com",
            client_id="cid", client_secret="secret",
        )
        d = p.to_dict()
        assert d["protocol"] == "oidc"
        assert d["client_secret"] == "***"

    def test_default_scopes(self):
        p = OIDCProvider(id="g", name="G", issuer_url="url", client_id="cid")
        assert "openid" in p.scopes
        assert "email" in p.scopes
        assert "profile" in p.scopes

    def test_custom_scopes(self):
        p = OIDCProvider(
            id="g", name="G", issuer_url="url", client_id="cid",
            scopes=["openid", "groups"],
        )
        assert p.scopes == ["openid", "groups"]


# --- SSOSession tests ---

class TestSSOSession:
    def test_create(self):
        s = SSOSession(
            id="sess1", user_id="u1", provider_id="okta",
            protocol=SSOProtocol.saml, token="sso_token",
        )
        assert s.id == "sess1"
        assert s.user_id == "u1"
        assert s.is_valid

    def test_expired(self):
        s = SSOSession(
            id="sess1", user_id="u1", provider_id="okta",
            protocol=SSOProtocol.saml,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert s.is_expired
        assert not s.is_valid

    def test_to_dict(self):
        s = SSOSession(id="s1", user_id="u1", provider_id="p1", protocol=SSOProtocol.oidc)
        d = s.to_dict()
        assert d["id"] == "s1"
        assert d["protocol"] == "oidc"
        assert "is_valid" in d


# --- SSOManager: Provider management ---

class TestSSOProviderManagement:
    def test_register_saml(self):
        mgr = SSOManager()
        p = SAMLProvider(id="okta", name="Okta", entity_id="eid", sso_url="url")
        mgr.register_saml_provider(p)
        assert mgr.get_saml_provider("okta") == p

    def test_register_oidc(self):
        mgr = SSOManager()
        p = OIDCProvider(id="google", name="Google", issuer_url="url", client_id="cid")
        mgr.register_oidc_provider(p)
        assert mgr.get_oidc_provider("google") == p

    def test_get_saml_not_found(self):
        mgr = SSOManager()
        with pytest.raises(SSOProviderNotFoundError):
            mgr.get_saml_provider("nonexistent")

    def test_get_oidc_not_found(self):
        mgr = SSOManager()
        with pytest.raises(SSOProviderNotFoundError):
            mgr.get_oidc_provider("nonexistent")

    def test_list_providers(self):
        mgr = SSOManager()
        mgr.register_saml_provider(SAMLProvider(id="s1", name="S1", entity_id="e", sso_url="u"))
        mgr.register_oidc_provider(OIDCProvider(id="o1", name="O1", issuer_url="i", client_id="c"))
        providers = mgr.list_providers()
        assert len(providers) == 2

    def test_remove_provider(self):
        mgr = SSOManager()
        mgr.register_saml_provider(SAMLProvider(id="s1", name="S1", entity_id="e", sso_url="u"))
        mgr.remove_provider("s1")
        with pytest.raises(SSOProviderNotFoundError):
            mgr.get_saml_provider("s1")

    def test_provider_count(self):
        mgr = SSOManager()
        assert mgr.provider_count == 0
        mgr.register_saml_provider(SAMLProvider(id="s1", name="S1", entity_id="e", sso_url="u"))
        mgr.register_oidc_provider(OIDCProvider(id="o1", name="O1", issuer_url="i", client_id="c"))
        assert mgr.provider_count == 2


# --- SSOManager: OIDC authentication ---

class TestOIDCAuthentication:
    def test_get_authorize_url(self):
        mgr = SSOManager()
        mgr.register_oidc_provider(OIDCProvider(
            id="google", name="Google", issuer_url="https://accounts.google.com",
            client_id="cid", authorize_url="https://accounts.google.com/o/oauth2/auth",
        ))
        url = mgr.get_oidc_authorize_url("google", "https://vsrs.local/callback")
        assert "accounts.google.com" in url
        assert "client_id=cid" in url
        assert "response_type=code" in url

    def test_validate_token_valid(self):
        mgr = SSOManager()
        mgr.register_oidc_provider(OIDCProvider(
            id="g", name="G", issuer_url="https://issuer.example.com",
            client_id="cid",
        ))
        jwt = _make_jwt({
            "sub": "user123",
            "email": "user@example.com",
            "iss": "https://issuer.example.com",
            "aud": "cid",
            "exp": int(time.time()) + 3600,
        })
        claims = mgr.validate_oidc_token("g", jwt)
        assert claims["sub"] == "user123"

    def test_validate_token_expired(self):
        mgr = SSOManager()
        mgr.register_oidc_provider(OIDCProvider(
            id="g", name="G", issuer_url="url", client_id="cid",
        ))
        jwt = _make_jwt({"sub": "u1", "exp": int(time.time()) - 100})
        with pytest.raises(SSOTokenExpiredError):
            mgr.validate_oidc_token("g", jwt)

    def test_validate_token_invalid_format(self):
        mgr = SSOManager()
        mgr.register_oidc_provider(OIDCProvider(id="g", name="G", issuer_url="url", client_id="cid"))
        with pytest.raises(SSOAuthenticationError):
            mgr.validate_oidc_token("g", "not.a.jwt")

    def test_authenticate_oidc(self):
        mgr = SSOManager()
        mgr.register_oidc_provider(OIDCProvider(
            id="google", name="Google", issuer_url="https://accounts.google.com",
            client_id="cid",
        ))
        jwt = _make_jwt({
            "sub": "ext123",
            "email": "user@example.com",
            "name": "Test User",
            "exp": int(time.time()) + 3600,
        })
        session = mgr.authenticate_oidc("google", jwt, userinfo={"name": "Test User"})
        assert session.user_id
        assert session.protocol == SSOProtocol.oidc
        assert session.is_valid
        assert session.token.startswith("sso_")

    def test_authenticate_oidc_provisions_user(self):
        mgr = SSOManager()
        mgr.register_oidc_provider(OIDCProvider(
            id="google", name="Google", issuer_url="url", client_id="cid",
        ))
        jwt = _make_jwt({
            "sub": "ext123", "email": "user@example.com", "exp": int(time.time()) + 3600,
        })
        session = mgr.authenticate_oidc("google", jwt)
        user = mgr.get_user(session.user_id)
        assert user is not None
        assert user.email == "user@example.com"

    def test_authenticate_oidc_same_user_second_time(self):
        mgr = SSOManager()
        mgr.register_oidc_provider(OIDCProvider(
            id="g", name="G", issuer_url="url", client_id="cid",
        ))
        jwt = _make_jwt({"sub": "ext1", "email": "u@e.com", "exp": int(time.time()) + 3600})
        s1 = mgr.authenticate_oidc("g", jwt)
        s2 = mgr.authenticate_oidc("g", jwt)
        assert s1.user_id == s2.user_id
        assert s1.id != s2.id  # Different sessions
        assert mgr.user_count == 1


# --- SSOManager: SAML authentication ---

class TestSAMLAuthentication:
    def test_get_redirect_url(self):
        mgr = SSOManager()
        mgr.register_saml_provider(SAMLProvider(
            id="okta", name="Okta", entity_id="eid", sso_url="https://okta.com/sso",
        ))
        url = mgr.get_saml_redirect_url("okta", relay_state="state123")
        assert "okta.com" in url
        assert "SAMLRequest=" in url
        assert "RelayState=state123" in url

    def test_validate_saml_response(self):
        mgr = SSOManager()
        mgr.register_saml_provider(SAMLProvider(
            id="okta", name="Okta", entity_id="eid", sso_url="url", audience="vsrs",
        ))
        response = _make_saml_response("user@example.com", "user@example.com")
        attrs = mgr.validate_saml_response("okta", response)
        assert "name_id" in attrs
        assert attrs["name_id"] == "user@example.com"

    def test_authenticate_saml(self):
        mgr = SSOManager()
        mgr.register_saml_provider(SAMLProvider(
            id="okta", name="Okta", entity_id="eid", sso_url="url", audience="vsrs",
        ))
        response = _make_saml_response("user@example.com", "user@example.com")
        session = mgr.authenticate_saml("okta", response)
        assert session.user_id
        assert session.protocol == SSOProtocol.saml
        assert session.is_valid

    def test_authenticate_saml_provisions_user(self):
        mgr = SSOManager()
        mgr.register_saml_provider(SAMLProvider(
            id="okta", name="Okta", entity_id="eid", sso_url="url", audience="vsrs",
        ))
        response = _make_saml_response("user@example.com", "user@example.com")
        session = mgr.authenticate_saml("okta", response)
        user = mgr.get_user(session.user_id)
        assert user is not None

    def test_authenticate_saml_invalid_response(self):
        mgr = SSOManager()
        mgr.register_saml_provider(SAMLProvider(
            id="okta", name="Okta", entity_id="eid", sso_url="url",
        ))
        with pytest.raises(SSOAuthenticationError):
            mgr.validate_saml_response("okta", "!!!invalid_base64!!!")


# --- SSOManager: Session management ---

class TestSSOSessionManagement:
    def test_get_session_by_token(self):
        mgr = SSOManager()
        mgr.register_oidc_provider(OIDCProvider(
            id="g", name="G", issuer_url="url", client_id="cid",
        ))
        jwt = _make_jwt({"sub": "u1", "exp": int(time.time()) + 3600})
        session = mgr.authenticate_oidc("g", jwt)
        found = mgr.get_session(session.token)
        assert found is not None
        assert found.id == session.id

    def test_get_session_invalid_token(self):
        mgr = SSOManager()
        assert mgr.get_session("nonexistent") is None

    def test_get_session_by_id(self):
        mgr = SSOManager()
        mgr.register_oidc_provider(OIDCProvider(id="g", name="G", issuer_url="url", client_id="cid"))
        jwt = _make_jwt({"sub": "u1", "exp": int(time.time()) + 3600})
        session = mgr.authenticate_oidc("g", jwt)
        found = mgr.get_session_by_id(session.id)
        assert found is not None

    def test_logout(self):
        mgr = SSOManager()
        mgr.register_oidc_provider(OIDCProvider(id="g", name="G", issuer_url="url", client_id="cid"))
        jwt = _make_jwt({"sub": "u1", "exp": int(time.time()) + 3600})
        session = mgr.authenticate_oidc("g", jwt)
        assert mgr.logout(session.token) is True
        assert mgr.get_session(session.token) is None

    def test_logout_invalid_token(self):
        mgr = SSOManager()
        assert mgr.logout("nonexistent") is False

    def test_refresh_session(self):
        mgr = SSOManager()
        mgr.register_oidc_provider(OIDCProvider(id="g", name="G", issuer_url="url", client_id="cid"))
        jwt = _make_jwt({"sub": "u1", "exp": int(time.time()) + 3600})
        session = mgr.authenticate_oidc("g", jwt)
        original_expiry = session.expires_at
        refreshed = mgr.refresh_session(session.id, extend_hours=12)
        assert refreshed.expires_at > original_expiry

    def test_refresh_session_not_found(self):
        mgr = SSOManager()
        with pytest.raises(SSOError):
            mgr.refresh_session("nonexistent")

    def test_cleanup_expired_sessions(self):
        mgr = SSOManager()
        mgr.register_oidc_provider(OIDCProvider(id="g", name="G", issuer_url="url", client_id="cid"))
        jwt = _make_jwt({"sub": "u1", "exp": int(time.time()) + 3600})
        session = mgr.authenticate_oidc("g", jwt)
        # Manually expire
        session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        removed = mgr.cleanup_expired_sessions()
        assert removed == 1
        assert mgr.get_session(session.token) is None

    def test_cleanup_no_expired(self):
        mgr = SSOManager()
        assert mgr.cleanup_expired_sessions() == 0

    def test_list_active_sessions(self):
        mgr = SSOManager()
        mgr.register_oidc_provider(OIDCProvider(id="g", name="G", issuer_url="url", client_id="cid"))
        jwt = _make_jwt({"sub": "u1", "exp": int(time.time()) + 3600})
        mgr.authenticate_oidc("g", jwt)
        mgr.authenticate_oidc("g", jwt)
        sessions = mgr.list_active_sessions()
        assert len(sessions) == 2

    def test_session_count(self):
        mgr = SSOManager()
        assert mgr.session_count == 0
        mgr.register_oidc_provider(OIDCProvider(id="g", name="G", issuer_url="url", client_id="cid"))
        jwt = _make_jwt({"sub": "u1", "exp": int(time.time()) + 3600})
        mgr.authenticate_oidc("g", jwt)
        assert mgr.session_count == 1


# --- SSOManager: User provisioning ---

class TestUserProvisioning:
    def test_provision_new_user(self):
        mgr = SSOManager()
        mgr.register_oidc_provider(OIDCProvider(id="g", name="G", issuer_url="url", client_id="cid"))
        jwt = _make_jwt({"sub": "ext1", "email": "new@user.com", "exp": int(time.time()) + 3600})
        session = mgr.authenticate_oidc("g", jwt)
        user = mgr.get_user(session.user_id)
        assert user is not None
        assert user.email == "new@user.com"
        assert user.metadata["sso_provider"] == "g"
        assert user.metadata["external_id"] == "ext1"

    def test_provision_updates_existing_user(self):
        mgr = SSOManager()
        mgr.register_oidc_provider(OIDCProvider(id="g", name="G", issuer_url="url", client_id="cid"))
        jwt1 = _make_jwt({"sub": "ext1", "email": "old@user.com", "exp": int(time.time()) + 3600})
        s1 = mgr.authenticate_oidc("g", jwt1)
        jwt2 = _make_jwt({"sub": "ext1", "email": "new@user.com", "exp": int(time.time()) + 3600})
        s2 = mgr.authenticate_oidc("g", jwt2)
        assert s1.user_id == s2.user_id
        user = mgr.get_user(s1.user_id)
        assert user.email == "new@user.com"

    def test_different_providers_create_different_users(self):
        mgr = SSOManager()
        mgr.register_oidc_provider(OIDCProvider(id="g", name="G", issuer_url="url", client_id="cid"))
        mgr.register_oidc_provider(OIDCProvider(id="a", name="A", issuer_url="url", client_id="cid2"))
        jwt = _make_jwt({"sub": "ext1", "email": "u@e.com", "exp": int(time.time()) + 3600})
        s1 = mgr.authenticate_oidc("g", jwt)
        s2 = mgr.authenticate_oidc("a", jwt)
        assert s1.user_id != s2.user_id
        assert mgr.user_count == 2

    def test_list_users(self):
        mgr = SSOManager()
        mgr.register_oidc_provider(OIDCProvider(id="g", name="G", issuer_url="url", client_id="cid"))
        jwt = _make_jwt({"sub": "ext1", "email": "u@e.com", "exp": int(time.time()) + 3600})
        mgr.authenticate_oidc("g", jwt)
        users = mgr.list_users()
        assert len(users) == 1

    def test_user_count(self):
        mgr = SSOManager()
        assert mgr.user_count == 0
        mgr.register_oidc_provider(OIDCProvider(id="g", name="G", issuer_url="url", client_id="cid"))
        jwt = _make_jwt({"sub": "ext1", "email": "u@e.com", "exp": int(time.time()) + 3600})
        mgr.authenticate_oidc("g", jwt)
        assert mgr.user_count == 1


# --- Module structure tests ---

class TestModuleStructure:
    def test_imports_from_enterprise(self):
        from vsrs.enterprise import (
            SSOManager,
            SAMLProvider,
            OIDCProvider,
            SSOSession,
            SSOProtocol,
            SSOError,
            SSOAuthenticationError,
            SSOTokenExpiredError,
            SSOProviderNotFoundError,
        )
        assert SSOManager is not None
        assert SAMLProvider is not None
        assert OIDCProvider is not None

    def test_sso_protocol_values(self):
        assert SSOProtocol.saml == "saml"
        assert SSOProtocol.oidc == "oidc"

    def test_sso_error_hierarchy(self):
        assert issubclass(SSOAuthenticationError, SSOError)
        assert issubclass(SSOTokenExpiredError, SSOError)
        assert issubclass(SSOProviderNotFoundError, SSOError)

    def test_logger_exists(self):
        from vsrs.enterprise.sso import logger
        assert logger is not None
