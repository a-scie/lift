# Release Process

## Preparation

### Version Bump and Changelog

1. Bump the version in at [`science/__init__.py`](science/__init__.py).
2. Run `nox && nox -epackage` as a sanity check on the state of the project.
3. Update [`CHANGES.md`](CHANGES.md) with any changes that are likely to be useful to consumers.
4. Open a PR with these changes and land it on https://github.com/a-scie/lift main.

## Release

### Push Release Tag

Sync a local branch with https://github.com/a-scie/jump main and confirm it has the version bump
and changelog update as the tip commit:

```
$ git log --stat -1 HEAD
commit 01f3a0a8c9c278f092f13ce802bb10e6d3a16696 (HEAD -> main, upstream/main, upstream/HEAD)
Author: John Sirois <john.sirois@gmail.com>
Date:   Wed May 17 10:26:46 2023 -0700

    Prepare the 0.1.0 release.

 .circleci/config.yml          | 70 ++++++++++++++++++++++++++++++++++++
 .github/workflows/release.yml | 98 ++++++++++++++++++++++++++++++++++++++++++++++++++
 CHANGES.md                    |  5 +++
 CONTRIBUTING.md               | 37 +++++++++++++++++++
 README.md                     |  5 +++
 RELEASE.md                    | 43 ++++++++++++++++++++++
 6 files changed, 258 insertions(+)
```

Tag the release as `v<version>` and push the tag to https://github.com/a-scie/lift main:

```
$ git tag --sign -am 'Release 0.1.0' v0.1.0
$ git push --tags https://github.com/a-scie/lift HEAD:main
```

The release is automated and will create a GitHub Release page at
[https://github.com/a-scie/lift/releases/tag/v&lt;version&gt;](
https://github.com/a-scie/lift/releases) with binaries for Linux, Mac and Windows.
