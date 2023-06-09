# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import pytest


def issue(issue_id: int, ignore: bool = False):
    """Marks a test with an issue link in pytest verbose (-v) output.

    This requires accepting an extra `issue` str argument in the decorated test function or
    else an extra `_` argument if `ignore` is set to `True`.
    """
    return pytest.mark.parametrize(
        "_" if ignore else "issue", [f"https://github.com/a-scie/lift/issues/{issue_id}"]
    )
