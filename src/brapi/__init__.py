"""
brapi — fluent BrAPI v2 Python client.
"""
from .__version__ import __version__
from .client import BrapiClient
from ._result import BrapiResult
from ._auth import build_auth, OAuth2ClientCredentialsAuth, OAuth2PasswordAuth

from .entities.germplasm import Germplasm, GermplasmQuery

__all__ = [
    "__version__",
    "BrapiClient",
    "BrapiResult",
    "build_auth",
    "OAuth2ClientCredentialsAuth",
    "OAuth2PasswordAuth",
    "Germplasm",
    "GermplasmQuery",
]
