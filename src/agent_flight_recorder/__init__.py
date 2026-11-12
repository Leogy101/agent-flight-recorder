"""A local, framework-independent recording format and Python capture SDK."""

from .privacy import PrivacyPolicy
from .recorder import Limits, Recorder
from ._version import __version__

__all__ = ["Limits", "PrivacyPolicy", "Recorder", "__version__"]
