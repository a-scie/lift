#!/usr/bin/env sh

set -eu

if [ "$(uname -m)" = "s390x" ]; then
      # This hack gets the PyPy provider working on this image. The old PyPy s390x distributions
      # dynamically link libffi at an older version than I've been able to find a multi-platform
      # image with s390x support for.
      ln -s /usr/lib/s390x-linux-gnu/libffi.so.8 /usr/lib/s390x-linux-gnu/libffi.so.6
fi