# Git workflow

Two people work in different folders, so conflicts are almost impossible:

| Person | Folders they touch |
|---|---|
| Jesús | `backend/`, `data/`, `algorithms/`, `tests/`, `docs/`, `.github/`, `README.md`, `.gitignore` |
| Aldo | `frontend/` (only) |

Golden rule: nobody modifies files in the other person's folder, and **before every `git push`, run `git pull`**.
A single stable `main`; short branches only if a change is large or experimental.

## Branches
- `main`: always stable (tests pass). It is the branch pushed to GitHub.
- Optional short branches for large changes or experiments, with a prefix by type:
  `feature/<topic>`, `fix/<topic>`, `docs/<topic>`.

## Daily work cycle
```bash
cd ~/GitHub/Ares_Pathfinder
git switch main
git pull origin main                 # fetch the latest from GitHub
# ... work ...
cd backend && python -m pytest -q    # tests must pass before saving
cd ..
git status                           # what changed; .venv/ or __pycache__/ must not appear
git add <specific files>             # avoid 'git add .' without checking status
git commit -m "feat(backend): short description"
git push origin main
```

## Large changes with a branch and Pull Request (recommended)
```bash
git switch -c feature/new-mola-region
# ... commits ...
git push -u origin feature/new-mola-region
# On GitHub: Compare & pull request -> review the diff yourself -> Merge pull request
git switch main && git pull origin main
```
Reviewing the diff in the Pull Request before merging serves as a self-review.

## Commit messages
Format: `type(scope): short description`.
Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `data`.
Usual scopes: `backend`, `frontend`, `data`, `algoritmo`, `integración`.

## Rules
1. One commit = one change that makes sense on its own (separate code, data and documentation).
2. Run `pytest` before every commit that touches code.
3. Before `git add`, check `git status`: `.venv/`, `__pycache__/`, `.zip` files,
   credentials or the raster `data/raw/mola/*.img` must not appear (`.gitignore` excludes them).
4. Do not upload passwords or tokens. GitHub does not accept the account password in Git:
   use a personal token (Settings -> Developer settings -> Personal access tokens).
5. Do not use `git push --force` on `main`.
6. If something goes wrong before the commit: `git restore <file>` undoes changes to a file.
