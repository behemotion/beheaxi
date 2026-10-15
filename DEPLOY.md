# DEPLOY — beheaxi

> Runbook: what an operator runs today. beheaxi is a build-time library, so its
> "deploy" is artifact publication: every version tag produces a GitHub Release
> carrying the sdist and wheel. Ports per
> [CONVENTIONS §7](../docs/CONVENTIONS.md#7-service-packaging--deploy); topology in
> `CONNECTIONS.md`. Dated verification logs live in `docs/history/`, not here.

## Shape

| | |
|---|---|
| Host | `github.com/behemotion/beheaxi` (GitHub Actions + Releases; nothing on local infra) |
| Runtime | `ubuntu-latest` runner, `uv 0.12.23`, Python 3.12 |
| App | n/a — build-time library, no port, no service |
| DB | n/a |
| Vhost | n/a — the live surface is the Release page and its artifacts |

## Prerequisites

- `main` clean, pushed, level with `origin/main` (land everything via the
  `land-clean` skill first).
- Local suite green (the block in `AGENTS.md` § Build / test): ruff, mypy,
  pytest, `beheaxi conformance "beheaxi" --json`.
- `gh` authenticated (`gh auth status`) — only needed for § Verify.

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
   `beheaxi conformance` against it, and creates the GitHub Release with
   both artifacts attached.

## Verify

No `/healthz` — this repo's live surface is the release artifacts. After the
workflow goes green (`gh run watch` or the Actions tab):

```
gh release view vX.Y.Z                       # lists beheaxi-X.Y.Z.tar.gz + beheaxi-X.Y.Z-py3-none-any.whl
gh release download vX.Y.Z -p '*.whl' -O /tmp/
uv venv /tmp/beheaxi-verify && uv pip install --python /tmp/beheaxi-verify /tmp/beheaxi-*.whl
/tmp/beheaxi-verify/bin/beheaxi conformance "/tmp/beheaxi-verify/bin/beheaxi" --json   # exits 0
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

## Configuration & secrets

None. The workflow uses the job-scoped `GITHUB_TOKEN` (`contents: write`)
only; no env vars, no registries, no credentials live anywhere.

| Env var | Purpose | Where the value lives |
|---|---|---|
| — | beheaxi ships no deploy-time configuration | — |

## Ops

- A release = `pyproject.toml` version + README upgrade note + annotated tag,
  pushed; the artifacts follow automatically. An unpushed tag is an unusable
  release.
- Distribution stays GitHub-only (git tags + Release artifacts); no PyPI.
  Reproducibility for consumers still comes from their `uv.lock`, which
  records the resolved commit SHA of the git dependency.
- Runner actions are pinned to full commit SHAs; Dependabot bumps them.
