"""Receipt import services (TD §12).

- ``imports``: submission, requeue and manual retry (API side).
- ``pipeline``: claim, fetch, parse, validate, persist, record the outcome (worker side).
- ``persistence``: canonical receipt → merchant, store, receipt and lines.
- ``receipts``: changes users make to stored receipts.
"""
