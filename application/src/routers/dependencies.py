"""FastAPI middlewares and dependencies (auth, domain routing, database session)."""

import hmac
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Request, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

from src.application.config import AppConfig
from src.infrastructure.documents.mongodb import Mongodb


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


class AllowedDomainMiddleware(BaseHTTPMiddleware):
    """
    FastAPI / Starlette Middleware validating the target medical domain (`?domain=...`
    or `X-Oncoflow-Domain` header) against `APP_ALLOWED_DOMAINS` for all `/api/` routes,
    and attaching `request.state.requested_domain`, `request.state.domain`, and
    `request.state.domain_config`.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/"):
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
