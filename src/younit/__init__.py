"""younit — Official Python SDK for the Younit Trading API."""

from younit._version import __version__ as __version__
from younit.client import Client as Client
from younit.enums import ChartPeriod as ChartPeriod
from younit.exceptions import (
    APIError as APIError,
)
from younit.exceptions import (
    AuthError as AuthError,
)
from younit.exceptions import (
    BadRequest as BadRequest,
)
from younit.exceptions import (
    ConfigError as ConfigError,
)
from younit.exceptions import (
    ConnectionFailed as ConnectionFailed,
)
from younit.exceptions import (
    EFGError as EFGError,
)
from younit.exceptions import (
    Forbidden as Forbidden,
)
from younit.exceptions import (
    InsufficientFunds as InsufficientFunds,
)
from younit.exceptions import (
    InvalidCredentials as InvalidCredentials,
)
from younit.exceptions import (
    InvalidOrder as InvalidOrder,
)
from younit.exceptions import (
    InvalidSymbol as InvalidSymbol,
)
from younit.exceptions import (
    NotFound as NotFound,
)
from younit.exceptions import (
    OrderError as OrderError,
)
from younit.exceptions import (
    OrderRejected as OrderRejected,
)
from younit.exceptions import (
    RateLimited as RateLimited,
)
from younit.exceptions import (
    ServerError as ServerError,
)
from younit.exceptions import (
    StreamingError as StreamingError,
)
from younit.exceptions import (
    SubscriptionFailed as SubscriptionFailed,
)
from younit.exceptions import (
    TokenExpired as TokenExpired,
)
from younit.exceptions import (
    Unauthorized as Unauthorized,
)
from younit.models.streaming import (
    IndexUpdate as IndexUpdate,
)
from younit.models.streaming import (
    MarketUpdate as MarketUpdate,
)
from younit.models.streaming import (
    OrderUpdate as OrderUpdate,
)
from younit.models.streaming import (
    Subscription as Subscription,
)
from younit.models.streaming import (
    SymbolUpdate as SymbolUpdate,
)
from younit.models.streaming import (
    TopMover as TopMover,
)
from younit.models.streaming import (
    TradeUpdate as TradeUpdate,
)

__all__ = [  # noqa: RUF022 — grouped by category, not alphabetically
    "__version__",
    "Client",
    "ChartPeriod",
    # Exceptions
    "EFGError",
    "AuthError",
    "InvalidCredentials",
    "TokenExpired",
    "APIError",
    "BadRequest",
    "Unauthorized",
    "Forbidden",
    "NotFound",
    "RateLimited",
    "ServerError",
    "OrderError",
    "OrderRejected",
    "InsufficientFunds",
    "InvalidOrder",
    "InvalidSymbol",
    "ConfigError",
    "StreamingError",
    "ConnectionFailed",
    "SubscriptionFailed",
    # Streaming models
    "Subscription",
    "SymbolUpdate",
    "IndexUpdate",
    "MarketUpdate",
    "TradeUpdate",
    "OrderUpdate",
    "TopMover",
]
