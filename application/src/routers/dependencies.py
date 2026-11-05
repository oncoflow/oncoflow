"""FastAPI middlewares and dependencies (auth, security headers, rate limiting, domain routing, database session)."""

from collections import defaultdict, deque
import hmac
from functools import lru_cache
import re
import threading
import time
from typing import Annotated
import uuid

from fastapi import Depends, Header, HTTPException, Query, Request, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

from src.application.config import AppConfig
from src.infrastructure.documents.mongodb import Mongodb

_SAFE_REQUEST_ID_RE = re.compile(r"^[a-zA-Z0-9._\-]{1,128}$")
_DOCS_PATHS = ("/docs", "/docs/oauth2-redirect", "/redoc", "/api/v1/openapi.json")
_SWAGGER_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "frame-ancestors 'none'; base-uri 'self'"
)
_RATE_LIMIT_LOCK = threading.Lock()
_RATE_LIMIT_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def reset_rate_limit_buckets() -> None:
    """Clear in-memory rate-limit buckets (used by unit tests)."""
    with _RATE_LIMIT_LOCK:
        _RATE_LIMIT_BUCKETS.clear()


@lru_cache(maxsize=1)
def get_base_config() -> AppConfig:
    """
    Process-wide base configuration (parsed once).

    Re-parsing AppConfig (env + .env + mkdir) on every request blocked the event loop
    inside the async middleware. A configuration change requires an API restart.
    """
    return AppConfig()


@lru_cache(maxsize=16)
def get_domain_scoped_config(domain: str) -> AppConfig:
    """Domain-scoped configuration, cached per domain."""
    return get_base_config().for_domain(domain)


_bearer_scheme = HTTPBearer(auto_error=False, description="APP_API_TOKEN")
_api_key_scheme = APIKeyHeader(
    name="X-API-Key", auto_error=False, description="APP_API_TOKEN"
)


def verify_api_token(
    bearer: Annotated[
        HTTPAuthorizationCredentials | None, Security(_bearer_scheme)
    ] = None,
    api_key: Annotated[str | None, Security(_api_key_scheme)] = None,
) -> None:
    """
    Require the shared API token (APP_API_TOKEN) on every API route.

    Accepted as `Authorization: Bearer <token>` or `X-API-Key: <token>`.
    When no token is configured (dev mode only, enforced at startup), access is open.
    """
    expected = get_base_config().api_token
    if expected is None:
        return
    provided = bearer.credentials if bearer else api_key
    if not provided or not hmac.compare_digest(
        provided.encode(), expected.get_secret_value().encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise.",
            headers={"WWW-Authenticate": "Bearer"},
        )


class ApiSecurityMiddleware(BaseHTTPMiddleware):
    """
    Hospital-grade HTTP security middleware for FastAPI:
    - Generates or sanitizes `X-Request-ID` correlation identifiers.
    - Enforces maximum payload size (`APP_API_MAX_BODY_BYTES`, HTTP 413).
    - Optionally enforces authentication on `/docs`, `/redoc`, and `/api/v1/openapi.json` (`APP_API_DOCS_REQUIRE_AUTH`).
    - Optionally enforces per-IP sliding-window rate limiting (`APP_API_RATE_LIMIT_ENABLED`, HTTP 429).
    - Injects strict HTTP security headers (`CSP`, `HSTS`, `X-Content-Type-Options`, `X-Frame-Options`,
      `Referrer-Policy`, `Permissions-Policy`, `COOP`, `CORP`, `Cache-Control: no-store`).
    """

    @staticmethod
    def _extract_bearer_or_api_key(request: Request) -> str | None:
        auth_header = request.headers.get("Authorization") or ""
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            if token:
                return token
        api_key = request.headers.get("X-API-Key")
        return api_key.strip() if api_key else None

    @staticmethod
    def _resolve_client_ip(request: Request) -> str:
        ip = "unknown"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                ip = first
        if ip == "unknown":
            real_ip = request.headers.get("X-Real-IP")
            if real_ip and real_ip.strip():
                ip = real_ip.strip()
            elif request.client and request.client.host:
                ip = request.client.host
        user = (
            request.headers.get("X-Oncoflow-User")
            or request.headers.get("X-Auth-Request-Preferred-Username")
            or request.headers.get("X-Auth-Request-User")
            or ""
        ).strip()
        return f"{ip}:{user}" if user else ip

    @staticmethod
    def _apply_security_headers(
        request: Request, response, base_conf: AppConfig, request_id: str
    ) -> None:
        response.headers["X-Request-ID"] = request_id
        api_sec = base_conf.api
        if not api_sec.security_headers_enabled:
            return

        path = request.url.path
        is_docs = path in _DOCS_PATHS
        is_pdf = path.endswith("/pdf") or path.endswith("/file")

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault(
            "X-Frame-Options", "SAMEORIGIN" if is_pdf else api_sec.frame_options
        )
        response.headers.setdefault("Referrer-Policy", api_sec.referrer_policy)
        response.headers.setdefault("Permissions-Policy", api_sec.permissions_policy)
        response.headers.setdefault("Cross-Origin-Opener-Policy", api_sec.coop_policy)
        response.headers.setdefault("Cross-Origin-Resource-Policy", api_sec.corp_policy)
        response.headers.setdefault(
            "Content-Security-Policy",
            _SWAGGER_CSP if is_docs else api_sec.csp_policy,
        )
        if not is_docs and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = api_sec.cache_control

        if api_sec.hsts_enabled or not base_conf.dev_mode:
            hsts = f"max-age={api_sec.hsts_max_age}"
            if api_sec.hsts_include_subdomains:
                hsts = f"{hsts}; includeSubDomains"
            response.headers.setdefault("Strict-Transport-Security", hsts)

    async def dispatch(self, request: Request, call_next):
        base_conf = get_base_config()
        api_sec = base_conf.api

        raw_req_id = (request.headers.get("X-Request-ID") or "").strip()
        request_id = (
            raw_req_id if _SAFE_REQUEST_ID_RE.match(raw_req_id) else str(uuid.uuid4())
        )
        request.state.request_id = request_id

        # Allow CORS preflight requests to pass through immediately
        if request.method == "OPTIONS":
            response = await call_next(request)
            self._apply_security_headers(request, response, base_conf, request_id)
            return response

        # 1. Enforce max request body size via Content-Length
        content_length = request.headers.get("Content-Length")
        if content_length:
            try:
                body_len = int(content_length)
            except ValueError:
                body_len = 0
            if body_len > api_sec.max_body_bytes:
                resp = JSONResponse(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content={
                        "detail": (
                            f"Payload trop volumineux ({body_len} octets). "
                            f"Limite autorisée : {api_sec.max_body_bytes} octets."
                        )
                    },
                )
                self._apply_security_headers(request, resp, base_conf, request_id)
                return resp

        # 2. Enforce optional authentication on OpenAPI / Swagger docs
        if (
            api_sec.docs_require_auth
            and base_conf.api_token is not None
            and request.url.path in _DOCS_PATHS
        ):
            provided = self._extract_bearer_or_api_key(request)
            expected = base_conf.api_token.get_secret_value()
            if not provided or not hmac.compare_digest(
                provided.encode(), expected.encode()
            ):
                resp = JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Authentification requise."},
                    headers={"WWW-Authenticate": "Bearer"},
                )
                self._apply_security_headers(request, resp, base_conf, request_id)
                return resp

        # 3. Enforce optional sliding-window per-IP rate limiting (exempting /health)
        if api_sec.rate_limit_enabled and request.url.path != "/health":
            client_ip = self._resolve_client_ip(request)
            now = time.monotonic()
            window = float(api_sec.rate_limit_window_seconds)
            max_reqs = api_sec.rate_limit_requests
            with _RATE_LIMIT_LOCK:
                bucket = _RATE_LIMIT_BUCKETS[client_ip]
                cutoff = now - window
                while bucket and bucket[0] <= cutoff:
                    bucket.popleft()
                if len(bucket) >= max_reqs:
                    retry_after = max(1, int(window - (now - bucket[0])))
                    resp = JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={
                            "detail": "Trop de requêtes. Veuillez réessayer ultérieurement."
                        },
                        headers={"Retry-After": str(retry_after)},
                    )
                    self._apply_security_headers(request, resp, base_conf, request_id)
                    return resp
                bucket.append(now)

        response = await call_next(request)
        self._apply_security_headers(request, response, base_conf, request_id)
        return response


class AllowedDomainMiddleware(BaseHTTPMiddleware):
    """
    FastAPI / Starlette Middleware validating the target medical domain (`?domain=...`
    or `X-Oncoflow-Domain` header) against `APP_ALLOWED_DOMAINS` for all `/api/` routes,
    and attaching `request.state.requested_domain`, `request.state.domain`, and
    `request.state.domain_config`.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method != "OPTIONS" and request.url.path.startswith("/api/"):
            base_conf = get_base_config()
            raw_domain = request.query_params.get("domain") or request.headers.get(
                "X-Oncoflow-Domain"
            )
            requested_domain = raw_domain.strip().lower() if raw_domain else None

            if (
                requested_domain
                and requested_domain not in base_conf.enabled_domains_list
            ):
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": f"Domaine '{requested_domain}' non autorisé."},
                )

            resolved_domain = (
                requested_domain or (base_conf.domain or "oncology").strip().lower()
            )
            if resolved_domain not in base_conf.enabled_domains_list:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "detail": (
                            f"Domaine par défaut '{resolved_domain}' non autorisé. "
                            f"Domaines configurés : {base_conf.enabled_domains_list}"
                        )
                    },
                )

            request.state.requested_domain = requested_domain
            request.state.domain = resolved_domain
            request.state.domain_config = get_domain_scoped_config(resolved_domain)

        response = await call_next(request)
        if hasattr(request.state, "domain"):
            response.headers["X-Oncoflow-Domain"] = request.state.domain
        return response


def get_domain_config(
    request: Request,
    domain: Annotated[
        str | None,
        Query(description="Domaine médical cible (ex: oncology, sma)"),
    ] = None,
    x_domain: Annotated[
        str | None,
        Header(
            alias="X-Oncoflow-Domain",
            description="En-tête optionnel pour sélectionner le domaine médical",
        ),
    ] = None,
) -> AppConfig:
    """
    FastAPI dependency returning the domain-scoped `AppConfig` already validated
    and attached by `AllowedDomainMiddleware` (with fallback if called outside middleware).
    """
    if hasattr(request.state, "domain_config"):
        return request.state.domain_config

    base_conf = get_base_config()
    target = (domain or x_domain or base_conf.domain or "oncology").strip().lower()
    if target not in base_conf.enabled_domains_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Domaine '{target}' non autorisé.",
        )
    return get_domain_scoped_config(target)


DomainConfigDep = Annotated[AppConfig, Depends(get_domain_config)]


def get_db(config: DomainConfigDep):
    """
    FastAPI dependency yielding the domain-scoped MongoDB handle.
    The underlying MongoClient is shared process-wide (closed at API shutdown).
    """
    if config.rcp.display_type == "mongodb":
        yield Mongodb(config)
    else:
        yield None


def require_db(db=Depends(get_db)):
    """Require an active MongoDB handle (raises 500 if unavailable)."""
    if db is None or not hasattr(db, "database"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La base de données MongoDB n'est pas configurée ou accessible.",
        )
    return db


def get_current_user_info(
    x_user: Annotated[
        str | None,
        Header(
            alias="X-Oncoflow-User",
            description="Trusted user identifier forwarded by the reverse proxy / BFF",
        ),
    ] = None,
    x_user_name: Annotated[
        str | None,
        Header(
            alias="X-Oncoflow-User-Name",
            description="Optional display name forwarded by the reverse proxy / BFF",
        ),
    ] = None,
    x_proxy_secret: Annotated[
        str | None,
        Header(
            alias="X-Oncoflow-Proxy-Secret",
            description="Shared secret authenticating reverse proxy / BFF identity headers",
        ),
    ] = None,
) -> dict[str, str | bool | None]:
    """
    Resolve `{username, display_name, is_admin}` from `X-Oncoflow-User` (+ optional
    `X-Oncoflow-User-Name`), honoured only when `X-Oncoflow-Proxy-Secret` matches
    `APP_PROXY_SECRET` via `hmac.compare_digest`.
    """
    base_conf = get_base_config()
    expected_secret = base_conf.proxy_secret
    proxy_ok = expected_secret is not None and hmac.compare_digest(
        (x_proxy_secret or "").encode(),
        expected_secret.get_secret_value().encode(),
    )
    username = (x_user or "").strip()
    if not proxy_ok or not username:
        return {
            "username": None,
            "display_name": None,
            "is_admin": False,
        }

    display_name = (x_user_name or "").strip() or username
    return {
        "username": username,
        "display_name": display_name,
        "is_admin": base_conf.is_admin(username, display_name),
    }


def require_admin(
    x_user: Annotated[
        str | None,
        Header(alias="X-Oncoflow-User"),
    ] = None,
    x_user_name: Annotated[
        str | None,
        Header(alias="X-Oncoflow-User-Name"),
    ] = None,
    x_proxy_secret: Annotated[
        str | None,
        Header(alias="X-Oncoflow-Proxy-Secret"),
    ] = None,
) -> None:
    """
    Enforce admin privileges on destructive endpoints.

    - When user headers (`X-Oncoflow-User`) are present (e.g. requests coming through the
      BFF / OAuth2 reverse proxy on behalf of a human user), the proxy secret must be
      valid AND the user must be listed in `APP_ADMIN_USERS` (`AppConfig.is_admin`).
    - When `X-Oncoflow-User` is absent, internal service-to-service calls (`QueueBroker`,
      worker, BFF service client) already authenticated via `APP_API_TOKEN` are permitted.
    """
    if x_user is None:
        return

    user_info = get_current_user_info(
        x_user=x_user,
        x_user_name=x_user_name,
        x_proxy_secret=x_proxy_secret,
    )
    if not user_info["is_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Droits d'administrateur requis.",
        )
