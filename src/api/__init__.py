# src/api/ -- the HTTP layer (PRODUCTION_EVOLUTION_PROMPT.md Phase 5, §4).
#
# "FastAPI service -- thin HTTP layer only." Handlers here validate input, call
# into `domain` or `evolution`, and shape a response. No business logic, because
# logic that lives in a route handler cannot be tested without a request object
# and cannot be shared with the CLI -- which is how blocker B6 happened.
#
# Extraction from the 1,400-line `app.py` monolith (B4) is IN PROGRESS: the
# Phase 3/5 routes live here, the older ones are still in `app.py`. Both are
# mounted by the composition root. See PROGRESS.md for what remains.
