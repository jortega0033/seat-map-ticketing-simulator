# Releasing

A release here is a Git tag on `main` after the release check ticket (epic #1, last child) has passed. There is no package to publish: the application has no installer and no dependency. Only the owner releases; agents never tag or create a release.

## Steps

1. Confirm `main` is green in CI (Linux and Windows, Python 3.12 and 3.13).
2. From a clean checkout of `main`, run `python -m unittest discover -s tests` and note the test count and Python version.
3. Start the server with `python -m seat_ticketing --data-dir <scratch dir> --port 0`, check `GET /api/v1/health` returns `{"status": "ok", "api_version": 1}`, and run the manual browser checks listed in `CLAUDE.md`. Delete the scratch directory afterwards.
4. Move the Unreleased entries in `CHANGELOG.md` under a new version heading with the date, in a pull request that the owner merges.
5. The owner tags the merge commit (`git tag -a vX.Y.Z -m "vX.Y.Z"`) and pushes the tag.
