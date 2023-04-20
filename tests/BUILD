# Copyright 2022 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

python_tests(
    extra_env_vars=[
        "BUILD_ROOT",
    ],
    overrides={
        "test_config.py": {
            "dependencies": [
                "./data/interpreter-groups.toml"
            ],
            "runtime_package_dependencies": [
                "science:main"
            ]
         }
    }
)

python_test_utils(
    name="test_utils",
)
