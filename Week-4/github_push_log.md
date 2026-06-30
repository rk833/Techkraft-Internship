# Week 4 Practice: Git & GitHub

A short log/checklist for the "Push code to GitHub" practice item.
This is a workflow exercise, not a code deliverable — the goal is to
actually go through the commit/push cycle, not just have files exist
in a folder.

## Checklist

- [ ] `git status` — confirm new Week 4 files are untracked
- [ ] `git add .`
- [ ] `git commit -m "Week 4: API practice, weather CLI, prompt notes"`
- [ ] `git push`
- [ ] Confirm files appear on GitHub (refresh repo page)
- [ ] (Optional, for extra practice) Create a branch instead of pushing to main:
  - `git checkout -b week4-practice`
  - push the branch
  - open a Pull Request and merge it

## Commands used

```bash
git status
git add .
git commit -m "Week 4: API practice, weather CLI, prompt notes"
git push origin main
```

## Notes / observations
- `git status` before adding is a good habit — it shows exactly what
  will be staged, which avoids accidentally committing unrelated files.
- Commit messages should describe *what changed*, not just "update" —
  makes it much easier to scan history later (relevant for when the
  capstone project history gets longer in Month 3).
- If working in a team repo later (e.g. for the capstone), branches +
  pull requests avoid overwriting teammates' work directly on `main`.