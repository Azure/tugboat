"""Sphinx configuration."""

# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

import toml

sys.path.insert(0, os.path.abspath("../src"))


project = "tugboat"

with open("../pyproject.toml", encoding="utf-8") as f:
    release = toml.load(f)["tool"]["poetry"]["version"]
    version = release

# ReStructuredText doesn't allow substitutions within an image directive.
# Instead do the substitution here.
rst_prolog = f"""
.. |version_badge| image:: https://img.shields.io/badge/version-{release}-success
   :target: https://artifactory.metaswitch.com/ui/packages/pypi:%2F%2Fpyqslog
   :alt: version {release}
"""

copyright = "2020"  # pylint: disable=redefined-builtin
html_logo = "_static/tugboat.png"

extensions = ["sphinx.ext.autodoc", "sphinx.ext.autosectionlabel", "sphinx_copybutton"]
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ["_build", ".venv", ".mypy_cache"]

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = "furo"
pygments_style = "onehalf-light"
pygments_dark_style = "onehalf-dark"
html_static_path = ["_static"]

autodoc_default_options = {"inherited-members": True, "member-order": "bysource"}
copybutton_prompt_text = ">>> "
