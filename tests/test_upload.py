import io
import pytest


def test_upload_valid_csv(client, auth_headers_user_a, sample_csv_bytes):
    files = {"file": ("bakery_sales.csv", io.BytesIO(sample_csv_bytes), "text/csv")}
    response = client.post("/api/v1/datasets/", headers=auth_headers_user_a, files=files)
    assert response.status_code == 202
    data = response.json()
    assert "id" in data
    assert data["name"] == "bakery_sales"
    assert data["status"] == "processing"


def test_upload_non_csv_rejected(client, auth_headers_user_a):
    files = {"file": ("document.pdf", io.BytesIO(b"%PDF-1.4 sample content"), "application/pdf")}
    response = client.post("/api/v1/datasets/", headers=auth_headers_user_a, files=files)
    assert response.status_code == 400
    assert "only .csv files are supported" in response.json()["detail"]


def test_upload_oversized_file_rejected(client, auth_headers_user_a):
    # Create 11 MB fake payload
    oversized = b"a" * (11 * 1024 * 1024)
    files = {"file": ("huge.csv", io.BytesIO(oversized), "text/csv")}
    response = client.post("/api/v1/datasets/", headers=auth_headers_user_a, files=files)
    assert response.status_code == 400
    assert "exceeds maximum allowed size" in response.json()["detail"]


def test_upload_empty_csv_rejected(client, auth_headers_user_a):
    files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    response = client.post("/api/v1/datasets/", headers=auth_headers_user_a, files=files)
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_list_datasets_pagination(client, auth_headers_user_a, sample_csv_bytes):
    # Upload 3 datasets
    for i in range(3):
        files = {"file": (f"sales_{i}.csv", io.BytesIO(sample_csv_bytes), "text/csv")}
        client.post("/api/v1/datasets/", headers=auth_headers_user_a, files=files)

    response = client.get("/api/v1/datasets/?page=1&page_size=2", headers=auth_headers_user_a)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total_pages"] == 2
