from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.application.config import AppConfig
from src.infrastructure.documents.mongodb import Mongodb


class AllowedDomainMiddleware(BaseHTTPMiddleware):
    """
    FastAPI / Starlette Middleware validating the target medical domain (`?domain=...`
    or `X-Oncoflow-Domain` header) against `APP_ALLOWED_DOMAINS` for all `/api/` routes,
    and attaching `request.state.requested_domain`, `request.state.domain`, and
    `request.state.domain_config`.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/"):
            base_conf = AppConfig()
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
                    content={
                        "detail": (
                            f"Domaine '{requested_domain}' non autorisé. "
                            f"Domaines configurés : {base_conf.enabled_domains_list}"
                        )
                    },
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
            request.state.domain_config = base_conf.for_domain(resolved_domain)

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

    base_conf = AppConfig()
    target = (domain or x_domain or base_conf.domain or "oncology").strip().lower()
    if target not in base_conf.enabled_domains_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Domaine '{target}' non autorisé. "
                f"Domaines configurés : {base_conf.enabled_domains_list}"
            ),
        )
    return base_conf.for_domain(target)


DomainConfigDep = Annotated[AppConfig, Depends(get_domain_config)]


def get_db(config: DomainConfigDep):
    """
    FastAPI dependency generator that yields the domain-scoped MongoDB client
    and ensures it is closed after the request finishes.
    """
    if config.rcp.display_type == "mongodb":
        client = Mongodb(config)
        try:
            yield client
        finally:
            client.close()
    else:
        yield None
