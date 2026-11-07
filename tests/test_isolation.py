import io
import pytest
from app.services.data_loader import process_dataset_background


def test_user_b_cannot_access_user_a_dataset(
    client,
    auth_headers_user_a,
    auth_headers_user_b,
    sample_csv_bytes,
):
    # User A uploads dataset
    files = {"file": ("priya_data.csv", io.BytesIO(sample_csv_bytes), "text/csv")}
    upload_resp = client.post("/api/v1/datasets/", headers=auth_headers_user_a, files=files)
    dataset_id = upload_resp.json()["id"]
    process_dataset_background(dataset_id)

    # 1. User B tries to get dataset details -> 404
    resp = client.get(f"/api/v1/datasets/{dataset_id}/", headers=auth_headers_user_b)
    assert resp.status_code == 404

    # 2. User B tries to get dataset profile -> 404
    resp = client.get(f"/api/v1/datasets/{dataset_id}/profile/", headers=auth_headers_user_b)
    assert resp.status_code == 404

    # 3. User B tries to query User A's dataset -> 404
    resp = client.post(
        f"/api/v1/datasets/{dataset_id}/query/",
        headers=auth_headers_user_b,
        json={"sql": "SELECT * FROM priya_data;"},
    )
    assert resp.status_code == 404

    # 4. User B tries to create share link for User A's dataset -> 404
    resp = client.post(
        f"/api/v1/datasets/{dataset_id}/share/",
        headers=auth_headers_user_b,
        json={},
    )
    assert resp.status_code == 404

    # 5. User B tries to delete User A's dataset -> 404
    resp = client.delete(f"/api/v1/datasets/{dataset_id}/", headers=auth_headers_user_b)
    assert resp.status_code == 404

    # 6. User B lists datasets -> User A's dataset is not included
    resp = client.get("/api/v1/datasets/", headers=auth_headers_user_b)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(item["id"] != dataset_id for item in items)
