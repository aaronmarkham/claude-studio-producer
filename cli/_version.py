"""Single source of truth for the package version.

Kept dependency-free so setuptools can read ``__version__`` statically at build
time (``[tool.setuptools.dynamic]`` in pyproject.toml) and the CLI can import it
at runtime for ``--version`` — no drift between the two, no reinstall required.
"""

__version__ = "0.8.0"
