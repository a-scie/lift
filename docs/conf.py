# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).
import os
import sys
from datetime import datetime
from pathlib import Path

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html


# N.B. This sneaks in a custom `science.dataclass.reflect.Ref` slugifier function that generates
# valid html anchor ids.
os.environ["_SCIENCE_REF_SLUGIFIER"] = "sphinx_science.directives:type_id"

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent / "_ext"))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import science

project = "Science"
version = f"{science.VERSION.major}.{science.VERSION.minor}"
release = f"{science.VERSION}"
copyright = f"{datetime.now().year}, Science project contributors"
author = "John Sirois"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

sys.path.insert(0, str(Path(__file__).parent / "_ext"))
extensions = [
    "sphinx_science",
    "myst_parser",
    "sphinx_click",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

templates_path = [
    "_templates",
]

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output
# https://myst-parser.readthedocs.io/en/latest/configuration.html
# https://vsalvino.github.io/sphinx-library/customize.html

from sphinx_science.render import Icon, Link, MarkdownParser

myst_enable_extensions = [*MarkdownParser.ENABLE_EXTENSIONS]

html_title = f"Science Docs (v{release})"
html_theme = "library"


GITHUB_ICON = Icon(
    light="_static/icons/github-16.png",
    sepia="_static/icons/github-16.png",
    dark="_static/icons/github-white-16.png",
)

_NEXT_LINK_ID = 0


def next_link_id() -> int:
    global _NEXT_LINK_ID
    next_id = _NEXT_LINK_ID
    _NEXT_LINK_ID += 1
    return next_id


def create_extra_link(url: str, icon: Icon | None = None) -> Link:
    return Link(id=f"__extra_link_{next_link_id()}", url=url, icon=icon)


html_theme_options = {
    "show_breadcrumbs": True,
    "typography": "book",
    "show_project_name": False,
    "description": "Build your executables using science.",
    "extra_links": {
        "Source Code": create_extra_link("https://github.com/a-scie/lift", GITHUB_ICON),
        "Issue Tracker": create_extra_link("https://github.com/a-scie/lift/issues", GITHUB_ICON),
        "Releases": create_extra_link("https://github.com/a-scie/lift/releases", GITHUB_ICON),
    },
}

html_show_sourcelink = True
html_show_sphinx = True
html_logo = "_static/icons/atom-200.png"
html_favicon = "_static/icons/atom.ico"
html_sidebars = {
    "**": [
        "about.html",  # Project name, description, etc.
        "searchbox.html",  # Search.
        "extralinks.html",  # Links specified in theme options.
        "globaltoc.html",  # Global table of contents.
        # "localtoc.html",  # Contents of the current page.
        "readingmodes.html",  # Light/sepia/dark color schemes.
        # "sponsors.html",  # Fancy sponsor links.
    ]
}
html_static_path = ["_static"]
