"""Tests for enterprise features (Phase 20)."""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from vsrs.enterprise import (
    APIKey,
    APIKeyManager,
    AuditEvent,
    AuditEventType,
    AuditLogger,
    AuthContext,
    Permission,
    RateLimitConfig,
    RateLimitResult,
    RateLimiter,
    Role,
    RoleManager,
    User,
    has_permission,
)


# --- User Tests ---

class TestUser:
    def test_creation(self):
        user = User(id="u1", username="alice", email="alice@example.com")
        assert user.id == "u1"
        assert user.username == "alice"
        assert user.role == "viewer"
        assert user.active is True

    def test_creation_with_role(self):
        user = User(id="u1", username="bob", role="admin")
        assert user.role == "admin"

    def test_to_dict(self):
        user = User(id="u1", username="alice", email="alice@example.com")
        d = user.to_dict()
        assert d["id"] == "u1"
        assert d["username"] == "alice"


# --- APIKey Tests ---

class TestAPIKey:
    def test_creation(self):
        key = APIKey(id="k1", key_hash="abc123", user_id="u1")
        assert key.id == "k1"
        assert key.is_valid is True

    def test_revoked_not_valid(self):
        key = APIKey(id="k1", key_hash="abc", user_id="u1", revoked=True)
        assert key.is_valid is False

    def test_expired_not_valid(self):
        key = APIKey(
            id="k1", key_hash="abc", user_id="u1",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert key.is_valid is False

    def test_not_expired_valid(self):
        key = APIKey(
            id="k1", key_hash="abc", user_id="u1",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert key.is_valid is True

    def test_to_dict(self):
        key = APIKey(id="k1", key_hash="abc", user_id="u1", name="test")
        d = key.to_dict()
        assert d["id"] == "k1"
        assert d["name"] == "test"
        assert d["is_valid"] is True


# --- AuthContext Tests ---

class TestAuthContext:
    def test_with_user(self):
        user = User(id="u1", username="alice", role="admin")
        ctx = AuthContext(user=user, authenticated=True)
        assert ctx.user_id == "u1"
        assert ctx.role == "admin"
        assert ctx.authenticated is True

    def test_empty(self):
        ctx = AuthContext()
        assert ctx.user_id is None
        assert ctx.role is None
        assert ctx.authenticated is False


# --- APIKeyManager Tests ---

class TestAPIKeyManager:
    def test_create_key(self):
        mgr = APIKeyManager()
        raw_key, key = mgr.create_key("u1", name="test-key")
        assert key.id.startswith("key_")
        assert key.user_id == "u1"
        assert key.name == "test-key"
        assert raw_key.startswith("vsrs_")
        assert key.key_hash != raw_key  # stored as hash

    def test_validate_success(self):
        mgr = APIKeyManager()
        raw_key, key = mgr.create_key("u1", name="test")
        validated = mgr.validate(raw_key)
        assert validated is not None
        assert validated.id == key.id
        assert validated.last_used is not None

    def test_validate_invalid_key(self):
        mgr = APIKeyManager()
        assert mgr.validate("invalid_key") is None

    def test_validate_revoked(self):
        mgr = APIKeyManager()
        raw_key, key = mgr.create_key("u1")
        mgr.revoke(key.id)
        assert mgr.validate(raw_key) is None

    def test_validate_expired(self):
        mgr = APIKeyManager()
        raw_key, key = mgr.create_key(
            "u1",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert mgr.validate(raw_key) is None

    def test_revoke(self):
        mgr = APIKeyManager()
        _, key = mgr.create_key("u1")
        assert mgr.revoke(key.id) is True
        assert mgr.get(key.id).revoked is True

    def test_revoke_not_found(self):
        mgr = APIKeyManager()
        assert mgr.revoke("nonexistent") is False

    def test_get(self):
        mgr = APIKeyManager()
        _, key = mgr.create_key("u1")
        assert mgr.get(key.id) is key
        assert mgr.get("nonexistent") is None

    def test_list_keys(self):
        mgr = APIKeyManager()
        mgr.create_key("u1")
        mgr.create_key("u1")
        mgr.create_key("u2")
        assert len(mgr.list_keys()) == 3
        assert len(mgr.list_keys(user_id="u1")) == 2
        assert len(mgr.list_keys(user_id="u2")) == 1

    def test_count(self):
        mgr = APIKeyManager()
        mgr.create_key("u1")
        mgr.create_key("u2")
        assert mgr.count() == 2

    def test_clear(self):
        mgr = APIKeyManager()
        mgr.create_key("u1")
        mgr.clear()
        assert mgr.count() == 0

    def test_scopes(self):
        mgr = APIKeyManager()
        _, key = mgr.create_key("u1", scopes=["task:read", "verify:run"])
        assert "task:read" in key.scopes
        assert "verify:run" in key.scopes


# --- Permission Tests ---

class TestPermission:
    def test_values(self):
        assert Permission.task_create.value == "task:create"
        assert Permission.admin_all.value == "admin:all"
        assert Permission.verify_run.value == "verify:run"


# --- Role Tests ---

class TestRole:
    def test_creation(self):
        role = Role(name="custom", description="Custom role", permissions={"task:read"})
        assert role.name == "custom"
        assert role.has("task:read") is True
        assert role.has("task:create") is False

    def test_to_dict(self):
        role = Role(name="custom", permissions={"task:read", "task:create"})
        d = role.to_dict()
        assert d["name"] == "custom"
        assert "task:read" in d["permissions"]


# --- RoleManager Tests ---

class TestRoleManager:
    def test_builtin_roles(self):
        rm = RoleManager()
        assert rm.get("viewer") is not None
        assert rm.get("developer") is not None
        assert rm.get("admin") is not None

    def test_viewer_permissions(self):
        rm = RoleManager()
        assert rm.check("viewer", "task:read") is True
        assert rm.check("viewer", "task:create") is False
        assert rm.check("viewer", "admin:all") is False

    def test_developer_permissions(self):
        rm = RoleManager()
        assert rm.check("developer", "task:create") is True
        assert rm.check("developer", "verify:run") is True
        assert rm.check("developer", "admin:users") is False

    def test_admin_permissions(self):
        rm = RoleManager()
        assert rm.check("admin", "admin:all") is True
        assert rm.check("admin", "admin:users") is True
        assert rm.check("admin", "task:delete") is True

    def test_register_custom_role(self):
        rm = RoleManager()
        role = Role(name="qa", description="QA engineer", permissions={"task:read", "verify:run"})
        rm.register(role)
        assert rm.get("qa") is not None
        assert rm.check("qa", "verify:run") is True
        assert rm.check("qa", "task:create") is False

    def test_role_inheritance(self):
        rm = RoleManager()
        role = Role(
            name="senior_dev",
            permissions={"task:delete"},
            parent="developer",
        )
        rm.register(role)
        # Should inherit developer permissions
        assert rm.check("senior_dev", "task:create") is True
        assert rm.check("senior_dev", "verify:run") is True
        # Plus own permissions
        assert rm.check("senior_dev", "task:delete") is True
        # But not admin
        assert rm.check("senior_dev", "admin:all") is False

    def test_resolve_permissions(self):
        rm = RoleManager()
        perms = rm.resolve_permissions("admin")
        assert "admin:all" in perms
        assert "task:create" in perms

    def test_resolve_permissions_unknown_role(self):
        rm = RoleManager()
        assert rm.resolve_permissions("nonexistent") == set()

    def test_list_roles(self):
        rm = RoleManager()
        roles = rm.list_roles()
        names = [r.name for r in roles]
        assert "viewer" in names
        assert "developer" in names
        assert "admin" in names

    def test_count(self):
        rm = RoleManager()
        assert rm.count() == 3  # builtins

    def test_get_not_found(self):
        rm = RoleManager()
        assert rm.get("nonexistent") is None


# --- has_permission Tests ---

class TestHasPermission:
    def test_admin_has_all(self):
        assert has_permission("admin", Permission.admin_all) is True

    def test_viewer_no_admin(self):
        assert has_permission("viewer", Permission.admin_all) is False

    def test_developer_can_verify(self):
        assert has_permission("developer", "verify:run") is True

    def test_unknown_role(self):
        assert has_permission("unknown", "task:read") is False


# --- AuditEvent Tests ---

class TestAuditEvent:
    def test_creation(self):
        event = AuditEvent(
            event_type="auth:login",
            user_id="u1",
            action="login",
            success=True,
        )
        assert event.event_type == "auth:login"
        assert event.success is True

    def test_to_dict(self):
        event = AuditEvent(event_type="task:create", user_id="u1")
        d = event.to_dict()
        assert d["event_type"] == "task:create"
        assert d["user_id"] == "u1"

    def test_to_jsonl(self):
        event = AuditEvent(event_type="auth:login", user_id="u1")
        line = event.to_jsonl()
        parsed = json.loads(line)
        assert parsed["event_type"] == "auth:login"


# --- AuditEventType Tests ---

class TestAuditEventType:
    def test_values(self):
        assert AuditEventType.auth_login.value == "auth:login"
        assert AuditEventType.task_create.value == "task:create"
        assert AuditEventType.rate_limit_hit.value == "rate_limit:hit"


# --- AuditLogger Tests ---

class TestAuditLogger:
    def test_log(self):
        al = AuditLogger()
        event = AuditEvent(event_type="auth:login", user_id="u1")
        al.log(event)
        assert al.count() == 1

    def test_log_event_convenience(self):
        al = AuditLogger()
        event = al.log_event(
            AuditEventType.auth_login,
            user_id="u1",
            action="login",
            success=True,
        )
        assert event.event_type == "auth:login"
        assert event.user_id == "u1"
        assert al.count() == 1

    def test_query_all(self):
        al = AuditLogger()
        al.log_event("auth:login", user_id="u1")
        al.log_event("task:create", user_id="u1")
        al.log_event("task:create", user_id="u2")
        results = al.query()
        assert len(results) == 3

    def test_query_by_user(self):
        al = AuditLogger()
        al.log_event("auth:login", user_id="u1")
        al.log_event("task:create", user_id="u2")
        results = al.query(user_id="u1")
        assert len(results) == 1
        assert results[0].user_id == "u1"

    def test_query_by_event_type(self):
        al = AuditLogger()
        al.log_event("auth:login", user_id="u1")
        al.log_event("task:create", user_id="u1")
        results = al.query(event_type="task:create")
        assert len(results) == 1
        assert results[0].event_type == "task:create"

    def test_query_by_resource(self):
        al = AuditLogger()
        al.log_event("task:update", user_id="u1", resource="task_123")
        al.log_event("task:update", user_id="u1", resource="task_456")
        results = al.query(resource="task_123")
        assert len(results) == 1

    def test_query_by_success(self):
        al = AuditLogger()
        al.log_event("auth:login", user_id="u1", success=True)
        al.log_event("auth:login", user_id="u1", success=False)
        success_results = al.query(success=True)
        failure_results = al.query(success=False)
        assert len(success_results) == 1
        assert len(failure_results) == 1

    def test_query_with_limit(self):
        al = AuditLogger()
        for i in range(10):
            al.log_event("task:create", user_id="u1")
        results = al.query(limit=5)
        assert len(results) == 5

    def test_query_most_recent_first(self):
        al = AuditLogger()
        al.log_event("task:create", user_id="u1", resource="first")
        al.log_event("task:create", user_id="u1", resource="second")
        results = al.query()
        assert results[0].resource == "second"

    def test_clear(self):
        al = AuditLogger()
        al.log_event("auth:login", user_id="u1")
        al.clear()
        assert al.count() == 0

    def test_max_events(self):
        al = AuditLogger(max_events=3)
        for i in range(5):
            al.log_event("task:create", user_id="u1")
        assert al.count() == 3  # only keeps most recent 3

    def test_file_logging(self, tmp_path):
        log_file = tmp_path / "audit.jsonl"
        al = AuditLogger(log_file=log_file)
        al.log_event("auth:login", user_id="u1")
        al.log_event("task:create", user_id="u1")
        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2
        parsed = json.loads(lines[0])
        assert parsed["event_type"] == "auth:login"

    def test_export_jsonl(self, tmp_path):
        al = AuditLogger()
        al.log_event("auth:login", user_id="u1")
        al.log_event("task:create", user_id="u1")
        export_path = tmp_path / "export.jsonl"
        count = al.export_jsonl(export_path)
        assert count == 2
        assert export_path.exists()


# --- RateLimitConfig Tests ---

class TestRateLimitConfig:
    def test_defaults(self):
        config = RateLimitConfig()
        assert config.requests_per_minute == 60
        assert config.requests_per_hour == 1000
        assert config.burst_size == 10

    def test_custom(self):
        config = RateLimitConfig(requests_per_minute=100, burst_size=20)
        assert config.requests_per_minute == 100
        assert config.burst_size == 20

    def test_to_dict(self):
        config = RateLimitConfig()
        d = config.to_dict()
        assert "requests_per_minute" in d


# --- RateLimitResult Tests ---

class TestRateLimitResult:
    def test_allowed(self):
        result = RateLimitResult(allowed=True, remaining=5)
        assert result.allowed is True
        assert result.remaining == 5

    def test_denied(self):
        result = RateLimitResult(allowed=False, retry_after=2.0)
        assert result.allowed is False
        assert result.retry_after == 2.0

    def test_to_dict(self):
        result = RateLimitResult(allowed=True, remaining=5)
        d = result.to_dict()
        assert d["allowed"] is True


# --- RateLimiter Tests -----

class TestRateLimiter:
    def test_allows_under_limit(self):
        rl = RateLimiter(RateLimitConfig(requests_per_minute=10, burst_size=10))
        result = rl.check("user1")
        assert result.allowed is True

    def test_denies_over_burst(self):
        rl = RateLimiter(RateLimitConfig(requests_per_minute=100, burst_size=3))
        for _ in range(3):
            rl.check("user1")
        result = rl.check("user1")
        assert result.allowed is False

    def test_separate_identifiers(self):
        rl = RateLimiter(RateLimitConfig(requests_per_minute=100, burst_size=2))
        rl.check("user1")
        rl.check("user1")
        # user1 at burst limit, user2 should still be allowed
        result = rl.check("user2")
        assert result.allowed is True

    def test_reset_specific(self):
        rl = RateLimiter(RateLimitConfig(requests_per_minute=100, burst_size=2))
        rl.check("user1")
        rl.check("user1")
        assert rl.check("user1").allowed is False
        rl.reset("user1")
        assert rl.check("user1").allowed is True

    def test_reset_all(self):
        rl = RateLimiter(RateLimitConfig(requests_per_minute=100, burst_size=2))
        rl.check("user1")
        rl.check("user2")
        rl.reset()
        assert rl.check("user1").allowed is True
        assert rl.check("user2").allowed is True

    def test_get_usage(self):
        rl = RateLimiter(RateLimitConfig(requests_per_minute=10, burst_size=5))
        rl.check("user1")
        rl.check("user1")
        usage = rl.get_usage("user1")
        assert usage["minute_used"] == 2
        assert usage["minute_limit"] == 10
        assert usage["burst_remaining"] == 3

    def test_result_has_remaining(self):
        rl = RateLimiter(RateLimitConfig(requests_per_minute=10, burst_size=5))
        result = rl.check("user1")
        assert result.remaining > 0

    def test_denied_has_retry_after(self):
        rl = RateLimiter(RateLimitConfig(requests_per_minute=100, burst_size=1))
        rl.check("user1")
        result = rl.check("user1")
        assert result.allowed is False
        assert result.retry_after > 0
