# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

import os

IS_WINDOWS = os.name == "nt"
EXE_EXT = ".exe" if IS_WINDOWS else ""
