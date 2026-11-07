import io
import pytest
from app.services.data_loader import process_dataset_background


def test_sharing_flow(client, auth_headers_user_a, auth_headers_user_b, sample_csv_bytes):
    # Upload and prepare dataset
    files = {"file": ("bakery_sales.csv", io.BytesIO(sample_csv_bytes), "text/csv")}
    upload_resp = client.post("/api/v1/datasets/", headers=auth_headers_user_a, files=files)
    dataset_id = upload_resp.json()["id"]
    process_dataset_background(dataset_id)

    # 1. Save a query
    save_resp = client.post(
        f"/api/v1/datasets/{dataset_id}/queries/",
        headers=auth_headers_user_a,
        json={"title": "City Count", "sql_text": "SELECT city, COUNT(*) AS total FROM bakery_sales GROUP BY city;"},
    )
    assert save_resp.status_code == 201
    query_id = save_resp.json()["id"]

    # 2. Create share link linked to saved query
    share_resp = client.post(
        f"/api/v1/datasets/{dataset_id}/share/",
        headers=auth_headers_user_a,
        json={"query_id": query_id},
    )
    assert share_resp.status_code == 201
    share_data = share_resp.json()
    token = share_data["token"]
    assert "share_url" in share_data

    # 3. Access shared link WITHOUT any authentication headers (public learner/mentor access)
    public_resp = client.get(f"/api/v1/shared/{token}/")
    assert public_resp.status_code == 200
    public_data = public_resp.json()
    assert public_data["dataset_name"] == "bakery_sales"
    assert public_data["profile"] is not None
    assert public_data["saved_query"] is not None
    assert public_data["query_result"] is not None
    assert public_data["query_result"]["row_count"] > 0

    # 4. User B attempts to revoke User A's share link -> 403 Forbidden
    unauthorized_revoke = client.delete(f"/api/v1/shares/{token}/", headers=auth_headers_user_b)
    assert unauthorized_revoke.status_code == 403

    # 5. User A revokes share link -> 200 OK
    revoke_resp = client.delete(f"/api/v1/shares/{token}/", headers=auth_headers_user_a)
    assert revoke_resp.status_code == 200

    # 6. Subsequent visit to revoked share link -> 404 Not Found
    revoked_visit = client.get(f"/api/v1/shared/{token}/")
    assert revoked_visit.status_code == 404
