"""A local, framework-independent recording format and Python capture SDK."""

from .privacy import PrivacyPolicy
from .recorder import Limits, Recorder

__version__ = "0.1.0"
__all__ = ["Limits", "PrivacyPolicy", "Recorder", "__version__"]
