# DEPLOY — beheaxi

> Runbook: what an operator runs today. beheaxi is a build-time library, so its
> "deploy" is artifact publication: every version tag produces a GitHub Release
> carrying the sdist and wheel **and** publishes both to PyPI. Ports per
> [CONVENTIONS §7](../docs/CONVENTIONS.md#7-service-packaging--deploy); topology in
> `CONNECTIONS.md`. Dated verification logs live in `docs/history/`, not here.

## Shape

| | |
|---|---|
| Host | `github.com/behemotion/beheaxi` (GitHub Actions + Releases; nothing on local infra) |
| Runtime | `ubuntu-latest` runner, `uv 0.12.23`, Python 3.12 |
| App | n/a — build-time library, no port, no service |
| DB | n/a |
| Vhost | n/a — the live surfaces are the Release page, its artifacts, and PyPI |
| PyPI | `pypi.org/project/beheaxi` — trusted publishing (OIDC), no tokens |

## Prerequisites

- `main` clean, pushed, level with `origin/main` (land everything via the
  `land-clean` skill first).
- Local suite green (the block in `AGENTS.md` § Build / test): ruff, mypy,
  pytest, `beheaxi conformance "beheaxi" --json`.
- `gh` authenticated (`gh auth status`) — only needed for § Verify.
- One-time only: the PyPI **trusted publisher** is registered as — project
  `beheaxi`, owner `behemotion`, repository `beheaxi`, workflow `release.yml`,
  environment `pypi`, default branch `main`. If PyPI ever rejects a publish
  with "not a trusted publisher", re-check exactly those fields.

## Deploy

1. Bump the **patch** version in `pyproject.toml` (minor/major needs the
   owner's explicit OK).
2. Add an upgrade-notes section for the new version to `README.md`
   (§ Upgrading), and update any stale "latest tag" mentions in
   `README.md` / `CONNECTIONS.md`.
3. Commit and push via the `land-clean` skill.
4. Cut and push the annotated tag — this triggers the release workflow:

   ```
   git tag -a vX.Y.Z -m "vX.Y.Z — <one-line headline>"
   git push origin vX.Y.Z
   ```

5. `.github/workflows/release.yml` then, with no operator action: runs the
   full check suite, asserts tag/version parity, `uv build`s the sdist +
   wheel, smoke-installs the wheel into a scratch venv and runs
   `beheaxi conformance` against it, creates the GitHub Release with both
   artifacts attached, and publishes them to PyPI via trusted publishing.

## Verify

No `/healthz` — this repo's live surfaces are the GitHub Release and PyPI.
After the workflow goes green (`gh run watch` or the Actions tab):

```
gh release view vX.Y.Z                       # lists beheaxi-X.Y.Z.tar.gz + beheaxi-X.Y.Z-py3-none-any.whl
gh release download vX.Y.Z -D /tmp/beheaxi-verify
uv venv /tmp/beheaxi-verify/venv && uv pip install --python /tmp/beheaxi-verify/venv /tmp/beheaxi-verify/beheaxi-*.whl
/tmp/beheaxi-verify/venv/bin/beheaxi conformance "/tmp/beheaxi-verify/venv/bin/beheaxi" --json   # exits 0

# and straight from the index:
uv venv /tmp/beheaxi-pypi && uv pip install --python /tmp/beheaxi-pypi beheaxi==X.Y.Z
/tmp/beheaxi-pypi/bin/beheaxi describe --json   # "version": "X.Y.Z"
```

## Rollback

Valid only before any consumer pins the tag (consumers pin tags; a pulled tag
is a broken release, exactly like an unpushed one):

```
gh release delete vX.Y.Z --yes
git push origin :refs/tags/vX.Y.Z
git tag -d vX.Y.Z
```

If the tag already escaped, do not move it — ship `vX.Y.(Z+1)` instead.
Never re-push a moved tag: the 2026-10-15 history rewrite showed what that
costs downstream (`uv.lock` pins the resolved SHA).

On PyPI the upload is permanent: files can never be deleted, only **yanked**
(project page → Manage releases → Yank). A yanked version still installs when
pinned exactly, so yank is a warning, not a fix — notify pinned clients and
ship `X.Y.(Z+1)`.

## Configuration & secrets

None in this repo. The workflow uses the job-scoped `GITHUB_TOKEN`
(`contents: write`) plus a PyPI **trusted publisher** claim (`id-token: write`,
environment `pypi`); no API tokens or passwords live anywhere. See
§ Prerequisites for the one-time registration.

| Env var | Purpose | Where the value lives |
|---|---|---|
| — | beheaxi ships no deploy-time configuration | — |

## Ops

- A release = `pyproject.toml` version + README upgrade note + annotated tag,
  pushed; the artifacts and PyPI upload follow automatically. An unpushed tag
  is an unusable release.
- Distribution: PyPI is the primary channel for clients; git tags and the
  GitHub Release artifacts remain as alternatives. `uv.lock` still gives
  reproducible installs (PyPI pins by file hash; git pins by commit SHA).
- Runner actions are pinned to full commit SHAs; Dependabot bumps them.
