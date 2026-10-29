"""
Database FastAPI dependency provider.

Note: HTTP middlewares (`AllowedDomainMiddleware`) and authentication/domain
dependencies (`verify_api_token`, `DomainConfigDep`, `get_domain_config`) live in
`src.routers.dependencies` and are re-exported here for backward compatibility.
"""

from src.routers.dependencies import (
    AllowedDomainMiddleware,
    DomainConfigDep,
    get_base_config,
    get_db,
    get_domain_config,
    get_domain_scoped_config,
    require_db,
    verify_api_token,
)

__all__ = [
    "AllowedDomainMiddleware",
    "DomainConfigDep",
    "get_base_config",
    "get_db",
    "get_domain_config",
    "get_domain_scoped_config",
    "require_db",
    "verify_api_token",
]
