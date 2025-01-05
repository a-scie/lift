# Contributing

The `science` tool is intended to be the primary tool used by applications to build scies. Although
the [`scie-jump`](https://github.com/a-scie/jump) provides everything needed to build a scie, it is
low-level and will always have some sharp corners, including its JSON lift manifest format.

Probably the most important ease-of-life improvement of `science` over direct `scie-jump` use is its
support of [provider](science/providers) plugins that know how to include appropriate interpreter
distributions to power the scie. If you know a particular interpreter ecosystem well and would like
to add `science` support for it, that would be wonderful.

Thank you in advance for your time and effort.

## Development Environment

Development uses [`uv`](https://docs.astral.sh/uv/getting-started/installation/). Install as you
best see fit.

## Development Cycle

You might want to open a [discussion](https://github.com/a-scie/lift/discussions) or [issue](
https://github.com/a-scie/lift/issues) to vet your idea first. It can often save overall effort and
lead to a better end result.

Before sending off changes you should run `uv run dev-cmd`. This formats, lints, type checks and
tests the code.

To test changes to the `science` binary you can either use `uv run dev-cmd run -- <args>` or else
run `uv run dev-cmd package` and test the resulting science binaries in `dist/`. Four files will be
produced there:
1. The science "thin" binary: `science-<os>-<arch>(.<ext>)`
2. The science "thin" binary fingerprint file: `science-<os>-<arch>(.<ext>).sha256`
3. The science "fat" binary: `science-fat-<os>-<arch>(.<ext>)`
4. The science "fat" binary fingerprint file: `science-fat-<os>-<arch>(.<ext>).sha256`

If you've made doc changes you can preview these with any of:
+ Run `uv run dev-cmd run -- doc open`.
+ Run `uv run dev-cmd doc` and open `docs/build/html/index.html`.
+ Run `uv run dev-cmd package` and then run the resulting science binary passing `doc open`.

When you're ready to get additional eyes on your changes, submit a [pull request](
https://github.com/a-scie/lift/pulls).

If you've made documentation changes you can render the site in the fork you used for the pull
request by navigating to the "Deploy Doc Site" action in your fork and running the workflow
manually. You do this using the "Run workflow" widget in the top row of the workflow run list,
selecting your PR branch and clicking "Run workflow". This will fail your first time doing this due
to a branch protection rule the "Deploy Doc Site" action automatically establishes to restrict doc
site deployments to the main branch. To fix this, navigate to "Environments" in your fork settings
and edit the "github-pages" branch protection rule, changing "Deployment Branches" from
"Selected branches" to "All branches" and then save the protection rules. You can now re-run the
workflow and should be able to browse to https://<your github id>.github.io/lift to browse the
deployed site with your changes incorporated. N.B.: The site will be destroyed when you delete your
PR branch.
