import io
import pytest
from app.services.data_loader import process_dataset_background


def test_profiling_and_data_loading(client, auth_headers_user_a, sample_csv_bytes):
    # Upload file
    files = {"file": ("bakery_sales.csv", io.BytesIO(sample_csv_bytes), "text/csv")}
    upload_resp = client.post("/api/v1/datasets/", headers=auth_headers_user_a, files=files)
    dataset_id = upload_resp.json()["id"]

    # Explicitly run background worker synchronously for test verification
    process_dataset_background(dataset_id)

    # Check dataset status
    detail_resp = client.get(f"/api/v1/datasets/{dataset_id}/", headers=auth_headers_user_a)
    assert detail_resp.status_code == 200
    dataset_data = detail_resp.json()
    assert dataset_data["status"] == "ready"
    assert dataset_data["row_count"] == 6

    # Check profile report endpoint
    profile_resp = client.get(f"/api/v1/datasets/{dataset_id}/profile/", headers=auth_headers_user_a)
    assert profile_resp.status_code == 200
    profile = profile_resp.json()

    assert profile["dataset_id"] == dataset_id
    assert profile["row_count"] == 6
    assert profile["column_count"] == 5
    assert profile["duplicate_rows"] == 1  # Exactly 1 duplicate row in sample

    cols_by_name = {col["name"]: col for col in profile["columns"]}
    assert "item" in cols_by_name
    assert "quantity" in cols_by_name
    assert "price" in cols_by_name

    # Check quantity null detection (1 null out of 6 rows = 16.67%)
    qty_profile = cols_by_name["quantity"]
    assert qty_profile["null_count"] == 1
    assert qty_profile["null_percentage"] == 16.67

    # Check price stats
    price_profile = cols_by_name["price"]
    assert price_profile["stats"]["min"] == 2.0
    assert price_profile["stats"]["max"] == 5.0
