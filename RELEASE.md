# Release Process

## Preparation

### Version Bump and Changelog

1. Bump the version in at [`science/__init__.py`](science/__init__.py).
2. Run `nox && nox -epackage` as a sanity check on the state of the project.
3. Update [`CHANGES.md`](CHANGES.md) with any changes that are likely to be useful to consumers.
4. Open a PR with these changes and land it on https://github.com/a-scie/lift main.

## Release

### Push Release Tag

Sync a local branch with https://github.com/a-scie/lift main and confirm it has the version bump
and changelog update as the tip commit:

```
$ git log --stat -1 HEAD
commit b46e245557f776594339e351ecf34e5c0fafb4d2 (HEAD -> main, upstream/main, upstream/HEAD)
Author: John Sirois <john.sirois@gmail.com>
Date:   Wed May 17 11:08:18 2023 -0700

    Fix the science binary URL in provenance.

 CHANGES.md            | 5 +++++
 RELEASE.md            | 2 +-
 science/__init__.py   | 2 +-
 science/build_info.py | 6 +++---
 science/lift.py       | 2 +-
 tests/test_exe.py     | 2 +-
 6 files changed, 12 insertions(+), 7 deletions(-)
```

Tag the release as `v<version>` and push the tag to https://github.com/a-scie/lift main:

```
$ git tag --sign -am 'Release 0.1.0' v0.1.0
$ git push --tags https://github.com/a-scie/lift HEAD:main
```

The release is automated and will create a GitHub Release page at
[https://github.com/a-scie/lift/releases/tag/v&lt;version&gt;](
https://github.com/a-scie/lift/releases) with binaries for Linux, Mac and Windows.
