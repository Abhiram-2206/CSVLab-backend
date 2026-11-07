import csv
import io
import pytest
from app.services.data_loader import process_dataset_background


def test_export_query_as_csv(client, auth_headers_user_a, sample_csv_bytes):
    # Upload and process dataset
    files = {"file": ("bakery_sales.csv", io.BytesIO(sample_csv_bytes), "text/csv")}
    upload_resp = client.post("/api/v1/datasets/", headers=auth_headers_user_a, files=files)
    dataset_id = upload_resp.json()["id"]
    process_dataset_background(dataset_id)

    # 1. Export with custom SQL
    custom_sql = "SELECT city, COUNT(*) AS count FROM bakery_sales GROUP BY city ORDER BY count DESC"
    export_resp = client.get(
        f"/api/v1/datasets/{dataset_id}/export/?sql={custom_sql}",
        headers=auth_headers_user_a,
    )
    assert export_resp.status_code == 200
    assert "text/csv" in export_resp.headers["content-type"]
    assert "attachment;" in export_resp.headers["content-disposition"]

    # Parse and verify CSV contents
    csv_text = export_resp.text
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    assert len(rows) > 0
    assert "city" in rows[0]
    assert "count" in rows[0]

    # 2. Export via saved query
    save_resp = client.post(
        f"/api/v1/datasets/{dataset_id}/queries/",
        headers=auth_headers_user_a,
        json={"title": "Croissants only", "sql_text": "SELECT * FROM bakery_sales WHERE item = 'Croissant';"},
    )
    query_id = save_resp.json()["id"]

    saved_export_resp = client.get(
        f"/api/v1/datasets/{dataset_id}/export/?query_id={query_id}",
        headers=auth_headers_user_a,
    )
    assert saved_export_resp.status_code == 200
    saved_rows = list(csv.DictReader(io.StringIO(saved_export_resp.text)))
    assert len(saved_rows) == 3  # 3 Croissant records in sample
    assert all(r["item"] == "Croissant" for r in saved_rows)
