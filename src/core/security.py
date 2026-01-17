"""Security hardening module for Project Agent."""

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

from ..core.config import get_config
from ..core.logging_ import get_logger

logger = get_logger(__name__)

config = get_config()


@dataclass
class SecurityConfig:
    """Security configuration."""
    rate_limit_requests: int = 100
    rate_limit_window: int = 60
    api_key_length: int = 32
    session_timeout: int = 3600
    max_failed_attempts: int = 5
    lockout_duration: int = 900
    enable_audit_log: bool = True
    secret_rotation_days: int = 30


@dataclass
class RateLimitInfo:
    """Rate limit information."""
    allowed: bool
    remaining: int
    reset_at: float
    limit: int


@dataclass
class AuditLogEntry:
    """Audit log entry."""
    timestamp: datetime
    user: str
    action: str
    resource: str
    success: bool
    details: Dict[str, Any]
    ip_address: Optional[str]


class SecurityManager:
    """Manages security for the application."""

    def __init__(self, config: Optional[SecurityConfig] = None):
        self.config = config or SecurityConfig()
        self._rate_limit_store: Dict[str, List[float]] = {}
        self._failed_attempts: Dict[str, List[float]] = {}
        self._lockout_store: Dict[str, float] = {}
        self._api_keys: Dict[str, datetime] = {}
        self._audit_log: List[AuditLogEntry] = []

    def generate_api_key(self) -> Tuple[str, str]:
        """Generate a new API key (returns key and hash)."""
        key = secrets.token_urlsafe(self.config.api_key_length)
        key_hash = hashlib.sha256(key.encode()).hexdigest()

        self._api_keys[key_hash] = datetime.utcnow() + timedelta(days=365)

        return key, key_hash

    def validate_api_key(self, key: str) -> bool:
        """Validate an API key."""
        key_hash = hashlib.sha256(key.encode()).hexdigest()

        if key_hash not in self._api_keys:
            return False

        if datetime.utcnow() > self._api_keys[key_hash]:
            del self._api_keys[key_hash]
            return False

        return True

    def check_rate_limit(
        self,
        identifier: str,
        max_requests: Optional[int] = None,
        window: Optional[int] = None,
    ) -> RateLimitInfo:
        """Check rate limit for an identifier."""
        max_req = max_requests or self.config.rate_limit_requests
        window_sec = window or self.config.rate_limit_window

        now = time.time()

        if identifier not in self._rate_limit_store:
            self._rate_limit_store[identifier] = []

        requests = [
            t for t in self._rate_limit_store[identifier]
            if now - t < window_sec
        ]

        self._rate_limit_store[identifier] = requests

        if len(requests) >= max_req:
            oldest = min(requests) if requests else now
            reset_at = oldest + window_sec

            return RateLimitInfo(
                allowed=False,
                remaining=0,
                reset_at=reset_at,
                limit=max_req,
            )

        requests.append(now)

        return RateLimitInfo(
            allowed=True,
            remaining=max_req - len(requests),
            reset_at=now + window_sec,
            limit=max_req,
        )

    def check_failed_attempts(self, identifier: str) -> Tuple[bool, int]:
        """Check for failed login attempts."""
        now = time.time()

        if identifier in self._lockout_store:
            if now < self._lockout_store[identifier]:
                return False, int(self._lockout_store[identifier] - now)
            del self._lockout_store[identifier]

        if identifier not in self._failed_attempts:
            self._failed_attempts[identifier] = []

        recent_failures = [
            t for t in self._failed_attempts[identifier]
            if now - t < self.config.lockout_duration
        ]

        self._failed_attempts[identifier] = recent_failures

        if len(recent_failures) >= self.config.max_failed_attempts:
            lockout_until = now + self.config.lockout_duration
            self._lockout_store[identifier] = lockout_until
            return False, int(self.config.lockout_duration)

        return True, 0

    def record_failed_attempt(self, identifier: str) -> None:
        """Record a failed attempt."""
        now = time.time()

        if identifier not in self._failed_attempts:
            self._failed_attempts[identifier] = []

        self._failed_attempts[identifier].append(now)

    def generate_secure_token(self, length: int = 32) -> str:
        """Generate a secure random token."""
        return secrets.token_urlsafe(length)

    def hash_password(self, password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        """Hash a password with salt."""
        if salt is None:
            salt = self.generate_secure_token(16)

        combined = f"{password}{salt}"
        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            combined.encode(),
            salt.encode(),
            100000,
        ).hex()

        return password_hash, salt

    def verify_password(
        self, password: str, password_hash: str, salt: str
    ) -> bool:
        """Verify a password against its hash."""
        new_hash, _ = self.hash_password(password, salt)
        return hmac.compare_digest(new_hash, password_hash)

    def create_signature(self, data: str, secret: str) -> str:
        """Create an HMAC signature for data."""
        return hmac.new(
            secret.encode(),
            data.encode(),
            hashlib.sha256,
        ).hexdigest()

    def verify_signature(
        self, data: str, signature: str, secret: str
    ) -> bool:
        """Verify an HMAC signature."""
        expected = self.create_signature(data, secret)
        return hmac.compare_digest(expected, signature)

    def audit_log(
        self,
        user: str,
        action: str,
        resource: str,
        success: bool,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """Add an entry to the audit log."""
        if not self.config.enable_audit_log:
            return

        entry = AuditLogEntry(
            timestamp=datetime.utcnow(),
            user=user,
            action=action,
            resource=resource,
            success=success,
            details=details or {},
            ip_address=ip_address,
        )

        self._audit_log.append(entry)

        if len(self._audit_log) > 10000:
            self._audit_log = self._audit_log[-5000:]

        logger.info(f"Audit: {user} - {action} - {resource} - {success}")

    def get_audit_logs(
        self,
        user: Optional[str] = None,
        action: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditLogEntry]:
        """Get filtered audit logs."""
        logs = self._audit_log

        if user:
            logs = [l for l in logs if l.user == user]

        if action:
            logs = [l for l in logs if l.action == action]

        if since:
            logs = [l for l in logs if l.timestamp >= since]

        return sorted(logs, key=lambda l: l.timestamp, reverse=True)[:limit]

    def rotate_secrets(self) -> List[str]:
        """Rotate all secrets that need rotation."""
        rotated = []

        secret_files = [
            ".env",
            "config.yaml",
        ]

        for secret_file in secret_files:
            file_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                secret_file
            )

            if os.path.exists(file_path):
                mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if datetime.utcnow() - mtime > timedelta(days=self.config.secret_rotation_days):
                    rotated.append(secret_file)
                    logger.info(f"Secret rotation needed: {secret_file}")

        return rotated

    def get_security_report(self) -> Dict[str, Any]:
        """Generate a security report."""
        now = time.time()

        rate_limited = sum(
            1 for store in self._rate_limit_store.values()
            if len([t for t in store if now - t < 60]) >= self.config.rate_limit_requests
        )

        locked_out = len(self._lockout_store)

        failed_by_user = {}
        for user, attempts in self._failed_attempts.items():
            recent = [t for t in attempts if now - t < 3600]
            if recent:
                failed_by_user[user] = len(recent)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "rate_limit_stores": len(self._rate_limit_store),
            "rate_limited_identifiers": rate_limited,
            "locked_out_identifiers": locked_out,
            "failed_attempts_by_user": failed_by_user,
            "active_api_keys": len(self._api_keys),
            "audit_log_entries": len(self._audit_log),
            "security_config": {
                "rate_limit_requests": self.config.rate_limit_requests,
                "rate_limit_window": self.config.rate_limit_window,
                "max_failed_attempts": self.config.max_failed_attempts,
                "lockout_duration": self.config.lockout_duration,
                "audit_log_enabled": self.config.enable_audit_log,
            },
        }


def require_rate_limit(
    max_requests: int = 100,
    window: int = 60,
    key_func: Optional[callable] = None,
):
    """Decorator to require rate limiting on a function."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            security = SecurityManager()
            identifier = key_func(*args, **kwargs) if key_func else "default"

            result = security.check_rate_limit(identifier, max_requests, window)

            if not result.allowed:
                return {
                    "error": "Rate limit exceeded",
                    "retry_after": int(result.reset_at - time.time()),
                }

            return await func(*args, **kwargs)

        return wrapper
    return decorator


def require_api_key(func):
    """Decorator to require API key authentication."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        security = SecurityManager()

        from fastapi import Request, HTTPException

        request = None
        for arg in args:
            if isinstance(arg, Request):
                request = arg
                break

        if not request:
            raise HTTPException(status_code=400, detail="Request not found")

        api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")

        if not api_key:
            raise HTTPException(status_code=401, detail="API key required")

        if not security.validate_api_key(api_key):
            raise HTTPException(status_code=403, detail="Invalid API key")

        return await func(*args, **kwargs)

    return wrapper
