# Agent Guardrails

- No production credentials; use `.env` and `.env.example` only.
- Prefer workspace tasks over ad-hoc commands.
- Avoid destructive commands (`rm -rf`, `git reset --hard`, force pushes).
- Default to running quick tests before full suites.
- Log meaningful decisions in `decisions.md` and update `context.md` after sessions.
- Keep prompts and scratch notes in this folder, not in code files.
