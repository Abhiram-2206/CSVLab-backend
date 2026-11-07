import io
import pytest
from app.services.data_loader import process_dataset_background


@pytest.fixture
def ready_dataset_id(client, auth_headers_user_a, sample_csv_bytes):
    files = {"file": ("bakery_sales.csv", io.BytesIO(sample_csv_bytes), "text/csv")}
    upload_resp = client.post("/api/v1/datasets/", headers=auth_headers_user_a, files=files)
    dataset_id = upload_resp.json()["id"]
    process_dataset_background(dataset_id)
    return dataset_id


def test_valid_select_query(client, auth_headers_user_a, ready_dataset_id):
    sql = "SELECT city, COUNT(*) AS count FROM bakery_sales GROUP BY city ORDER BY count DESC"
    response = client.post(
        f"/api/v1/datasets/{ready_dataset_id}/query/",
        headers=auth_headers_user_a,
        json={"sql": sql},
    )
    assert response.status_code == 200
    data = response.json()
    assert "columns" in data
    assert "rows" in data
    assert "city" in data["columns"]
    assert "count" in data["columns"]
    assert data["row_count"] > 0
    assert data["truncated"] is False


def test_reject_drop_table(client, auth_headers_user_a, ready_dataset_id):
    sql = "DROP TABLE bakery_sales;"
    response = client.post(
        f"/api/v1/datasets/{ready_dataset_id}/query/",
        headers=auth_headers_user_a,
        json={"sql": sql},
    )
    assert response.status_code == 400
    assert "Forbidden keyword 'DROP'" in response.json()["detail"] or "Only SELECT" in response.json()["detail"]


def test_reject_update(client, auth_headers_user_a, ready_dataset_id):
    sql = "UPDATE bakery_sales SET price = 100;"
    response = client.post(
        f"/api/v1/datasets/{ready_dataset_id}/query/",
        headers=auth_headers_user_a,
        json={"sql": sql},
    )
    assert response.status_code == 400
    assert "Forbidden keyword 'UPDATE'" in response.json()["detail"] or "Only SELECT" in response.json()["detail"]


def test_reject_delete(client, auth_headers_user_a, ready_dataset_id):
    sql = "DELETE FROM bakery_sales WHERE price < 3;"
    response = client.post(
        f"/api/v1/datasets/{ready_dataset_id}/query/",
        headers=auth_headers_user_a,
        json={"sql": sql},
    )
    assert response.status_code == 400
    assert "Forbidden keyword 'DELETE'" in response.json()["detail"] or "Only SELECT" in response.json()["detail"]


def test_reject_multiple_statements(client, auth_headers_user_a, ready_dataset_id):
    sql = "SELECT * FROM bakery_sales; SELECT * FROM bakery_sales;"
    response = client.post(
        f"/api/v1/datasets/{ready_dataset_id}/query/",
        headers=auth_headers_user_a,
        json={"sql": sql},
    )
    assert response.status_code == 400
    assert "Multiple statements" in response.json()["detail"]


def test_reject_access_to_protected_tables(client, auth_headers_user_a, ready_dataset_id):
    sql = "SELECT * FROM users;"
    response = client.post(
        f"/api/v1/datasets/{ready_dataset_id}/query/",
        headers=auth_headers_user_a,
        json={"sql": sql},
    )
    assert response.status_code == 400
    assert "protected system/application table" in response.json()["detail"]


def test_row_cap_enforcement(client, auth_headers_user_a):
    # Create dataset with 1,200 rows
    rows = ["id,value"] + [f"{i},val_{i}" for i in range(1200)]
    large_csv = "\n".join(rows).encode("utf-8")
    
    files = {"file": ("large_data.csv", io.BytesIO(large_csv), "text/csv")}
    upload_resp = client.post("/api/v1/datasets/", headers=auth_headers_user_a, files=files)
    dataset_id = upload_resp.json()["id"]
    process_dataset_background(dataset_id)

    # Query all rows
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/query/",
        headers=auth_headers_user_a,
        json={"sql": "SELECT * FROM large_data;"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["row_count"] == 1000  # Capped at MAX_QUERY_ROWS = 1000
    assert data["truncated"] is True


def test_reject_saving_invalid_query(client, auth_headers_user_a, ready_dataset_id):
    # Attempting to save a query with a nonexistent table or broken syntax
    response = client.post(
        f"/api/v1/datasets/{ready_dataset_id}/queries/",
        headers=auth_headers_user_a,
        json={"title": "Broken Query", "sql_text": "SELECT * FROM nonexistent_table\\"},
    )
    assert response.status_code == 400
    assert "Cannot save invalid query" in response.json()["detail"]

