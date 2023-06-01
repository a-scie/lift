# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import sys
from datetime import datetime
from pathlib import Path
from textwrap import dedent

sys.path.insert(0, str(Path(__file__).parent.parent))
import science

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Science"
version = f"{science.VERSION.major}.{science.VERSION.minor}"
release = f"{science.VERSION}"
copyright = f"{datetime.now().year}, Science project contributors"
author = "John Sirois"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "myst_parser",
    "sphinx_click",
]
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output
# https://vsalvino.github.io/sphinx-library/customize.html

html_theme = "library"


EXTRA_LINK_IMG_ID = 0


def create_extra_link(
    text: str, url: str, light_icon: str, sepia_icon: str, dark_icon: str
) -> tuple[str, str]:
    global EXTRA_LINK_IMG_ID
    img_id = f"__extra_link_img_{EXTRA_LINK_IMG_ID}"
    EXTRA_LINK_IMG_ID += 1
    return (
        dedent(
            f"""\
            <div>
                <img id="{img_id}" style="vertical-align:middle" src="{light_icon}">
                <span style="padding-left:2px">{text}</span>
            </div>
            <script>
                # N.B.: The other half of this is implemented in `_static/js/icon_theme.js`.
                Science.theme.registerIcons(
                    "{img_id}", "{light_icon}", "{sepia_icon}", "{dark_icon}"
                );
            </script>
            """
        ),
        url,
    )


def create_extra_gh_link(text: str, url: str) -> tuple[str, str]:
    return create_extra_link(
        text,
        url,
        dark_icon="_static/icons/github-white-16.png",
        sepia_icon="_static/icons/github-16.png",
        light_icon="_static/icons/github-16.png",
    )


html_theme_options = {
    "show_breadcrumbs": True,
    "typography": "book",
    "show_project_name": False,
    "description": "Build your executables using science.",
    "extra_links": dict(
        (
            create_extra_gh_link("Source Code", "https://github.com/a-scie/lift"),
            create_extra_gh_link("Issue Tracker", "https://github.com/a-scie/lift/issues"),
            create_extra_gh_link("Releases", "https://github.com/a-scie/lift/releases"),
        )
    ),
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
        "localtoc.html",  # Contents of the current page.
        "readingmodes.html",  # Light/sepia/dark color schemes.
        # "sponsors.html",  # Fancy sponsor links.
    ]
}
html_static_path = ["_static"]
html_js_files = ["js/icon_theme.js"]
