---
name: milestone-check
description: Verify an Eksoda implementation milestone (M1-M6) against its tasks and exit criteria in docs/implementation-plan.md, run the full check suite in Docker, and update the docs with status and deviations. Use when finishing a milestone or when asked "is M<n> done?".
---

# Milestone check

1. Open `docs/implementation-plan.md` and find the milestone's
   **Tasks**, **Tests** and **Exit** sections.
2. For each task, find the implementing code (cite `path:line`). Mark it
   done, partial or missing. Do not mark a task done on the strength of
   a file merely existing.
3. Run the checks in Docker:

   ```bash
   make build
   make check
   make up
   docker compose ps    # all services healthy or completed
   ```

   Then exercise the exit criteria. For example, for M1:
   `curl -s localhost:8000/healthz`, `curl -s localhost:8000/readyz`,
   and the Swagger UI at `/api/docs/`. Stop the stack afterwards if you
   started it (`make down`).
4. Compare the code with `docs/requirements.md` and
   `docs/technical-design.md`. Wherever the code intentionally differs,
   update the doc rather than leaving the difference silent.
5. Update `docs/implementation-plan.md`:
   - the status table (§6), with the milestone, the date and a one-line
     summary
   - the known gaps carried into the next milestone
6. Report:
   - what was verified, with the commands and their results
   - what was not verified
   - the deviations recorded

   Never claim a check passed without having run it.
