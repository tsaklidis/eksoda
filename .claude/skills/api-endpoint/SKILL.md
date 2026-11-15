---
name: api-endpoint
description: Checklist for adding or changing an Eksoda REST API endpoint (DRF view, serializer, URL, OpenAPI, household isolation, tests). Use whenever a route under /api/v1 is created, renamed, or its request/response/permissions change.
---

# Add or change an API endpoint

Work through this list in order, and do not skip steps. The endpoint's
contract comes from `docs/requirements.md` §12. If the code must differ
from it, update the doc in the same change.

## 1. Contract first

- Find the endpoint in `docs/requirements.md` §12 and in the route table
  of `docs/technical-design.md` §14.
- Settle the method, path (no trailing slash), request fields, response
  fields, status codes and error codes before writing code.
- Any new error code needs:
  - an `ApiError` subclass with a stable `default_code`
  - a line in the docs

## 2. Service

- Put the business logic in the app's `services.py`, as a function with
  explicit arguments (`household=…`, `user=…`).
- Wrap multi-row writes in `transaction.atomic()`.
- Raise `ApiError` subclasses, never bare `ValidationError`, for domain
  rules.

## 3. View

- **Header-scoped data** (receipts, products, analytics): mix in
  `HouseholdScopedMixin`. Set `household_lookup` when the model reaches
  the household through a relation, e.g. `"receipt__household"`. Never
  build an unscoped queryset.
- **Path-scoped household routes:** use
  `households.services.get_membership_or_404()`, and `require_owner()`
  where the route is owner-only.
- Keep the view thin: validate with a serializer, call the service,
  serialize the result.
- Prevent N+1 queries with `select_related` / `prefetch_related` on
  lists.

## 4. Serializer

- List `fields` explicitly; never use `__all__`. Mark read-only fields.
- Money is a `DecimalField` (serialized as a string) next to a
  `currency` field.
- Never expose receipt URLs except `source_url` on receipt detail.

## 5. URL and schema

- Add the route to the app's `api/urls.py` with a unique name. The
  route is reached as `api-v1:<name>`.
- Add `@extend_schema(...)` where drf-spectacular cannot infer the
  request or response (APIViews, custom actions).
- `tests/test_schema.py` must still pass. It fails on schema warnings.

## 6. Tests (in `backend/tests/<app>/`)

- Happy path, validation errors, permission errors (member vs owner),
  401 without a token.
- **Isolation:** register the route in `tests/test_isolation.py`, either
  in `ISOLATION_CASES` (path- or header-scoped) or in
  `NOT_HOUSEHOLD_SCOPED` with a reason. Unregistered routes fail the
  suite. Routes without an object id (lists, create) set `hidden=` to an
  id of household B's that must not appear in the response; routes with
  an id expect `404`. Extend the `Foreign` fixture with the new object.
- Query count on list endpoints (`django_assert_max_num_queries`).

## 7. Finish

- Run `make check`.
- Update the docs if the contract changed.
