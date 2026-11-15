"""The OpenAPI schema is the API contract (D17): it must generate cleanly."""

import pytest
from django.core.management import call_command


def test_openapi_schema_is_valid_without_warnings(tmp_path):
    call_command(
        "spectacular", "--validate", "--fail-on-warn", "--file", str(tmp_path / "schema.yaml")
    )
    schema = (tmp_path / "schema.yaml").read_text()
    assert "/api/v1/auth/login" in schema
    assert "/api/v1/households/{household_id}/invitations" in schema
    assert "/api/v1/receipts/import" in schema
    assert "/api/v1/receipt-imports/{id}/retry" in schema
    assert "/api/v1/products/{id}/price-comparison" in schema
    for path in ("summary", "spending-by-category", "monthly-trend", "top-products"):
        assert f"/api/v1/analytics/{path}" in schema
    assert "/api/v1/categories/{id}" in schema
    assert "/api/v1/merchants/{id}" in schema
    assert "/api/v1/receipt-items/{id}/create-product" in schema
    assert "submitted_url" not in schema  # receipt URLs are credentials
    assert schema.count("name: X-Household-ID") >= 25  # every household-scoped operation


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/api/schema/", "/api/docs/"])
def test_schema_and_swagger_ui_are_served(client, path):
    assert client.get(path).status_code == 200
