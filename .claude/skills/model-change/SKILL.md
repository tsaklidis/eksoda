---
name: model-change
description: Checklist for adding or changing Eksoda Django models and migrations (constraints, household ownership, Decimal fields, admin, migration review). Use whenever models.py changes or a migration is created.
---

# Add or change models and migrations

## 1. Design check

- Compare the change with the model listing in `docs/technical-design.md`
  §7–§8 and `docs/requirements.md` §8. Update both docs if the model
  differs.
- Household-owned data has a direct `household` FK (CASCADE), or a
  mandatory parent that has one.
- Extend `apps.common.models.UUIDModel` for any API-visible entity.
- **Money and quantities:** use the `Decimal` field factories from
  `apps/common/fields.py`, with precision per requirements §10.1. Never
  use `FloatField`.
- Choices are `TextChoices` defined on the model.
- **Integrity rules belong in the database:** `UniqueConstraint`
  (partial with `condition=`, or `nulls_distinct=False`), and
  `CheckConstraint`. Give every constraint and index an explicit `name`.
- Add an index for every common filter, such as
  `(household, -issued_at)`.
- Cross-app FKs use string references (`"products.Product"`).

## 2. Migrations

- Generate with `make makemigrations`. Never hand-write schema
  migrations.
- Read the generated file. Check that no unintended table rewrite or
  data loss happens, and that the constraint names are right.
- **Data migrations** (seeds, backfills):
  - Must be idempotent (`update_or_create` by a natural key).
  - Use `apps.get_model`, never direct imports.
  - Provide `reverse_code` (`migrations.RunPython.noop` is acceptable
    for seeds).
- **Postgres extensions** (`pg_trgm`, `unaccent`) are already created in
  `common/0001`, but the MVP does not use them (D15). Do not add
  trigram indexes unless the docs are updated first.
- After the first production deploy, migrations are forward-only. Do not
  edit applied migrations.

## 3. Admin

- Register the model in the app's `admin.py`, with `list_display`,
  `list_filter`, `search_fields`, and `readonly_fields` for source data.

## 4. Tests

- Constraint tests: duplicates raise `IntegrityError` (use
  `transaction.atomic()` inside the test).
- Factories in `tests/factories.py` for the new models.
- If the model is household-scoped, extend the isolation cases for its
  endpoints.

## 5. Finish

- `make check`. This includes `makemigrations --check`, so a missing
  migration fails.
