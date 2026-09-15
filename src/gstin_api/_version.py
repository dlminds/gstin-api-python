"""Single source of truth for the version.

``pyproject.toml`` reads it from here (``[tool.hatch.version]``) so the number
is never written down twice, and the client can put it in a User-Agent without
importing the package into itself.
"""

__version__ = "0.1.0"
