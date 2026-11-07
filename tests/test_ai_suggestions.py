import io
from unittest.mock import MagicMock, patch
import pytest
from app.services.data_loader import process_dataset_background
from app.config import settings


def test_ai_suggestions_heuristic_fallback(client, auth_headers_user_a, sample_csv_bytes):
    # Ensure no Groq key for fallback test
    with patch.object(settings, "GROQ_API_KEY", None):
        files = {"file": ("bakery_sales.csv", io.BytesIO(sample_csv_bytes), "text/csv")}
        upload_resp = client.post("/api/v1/datasets/", headers=auth_headers_user_a, files=files)
        dataset_id = upload_resp.json()["id"]
        process_dataset_background(dataset_id)

        response = client.post(f"/api/v1/datasets/{dataset_id}/suggestions/", headers=auth_headers_user_a)
        assert response.status_code == 200
        data = response.json()
        assert data["dataset_id"] == dataset_id
        assert len(data["suggestions"]) == 5
        for item in data["suggestions"]:
            assert item["question"]
            assert item["sql"].startswith("SELECT")
            assert item["rationale"]


def test_ai_suggestions_privacy_no_raw_rows_sent(client, auth_headers_user_a, sample_csv_bytes):
    """
    CRITICAL PRIVACY TEST:
    Assert that the payload sent to Groq contains ONLY column metadata/stats,
    and NEVER contains raw row values like 'Croissant', 'Bangalore', or 'Muffin'.
    """
    files = {"file": ("bakery_sales.csv", io.BytesIO(sample_csv_bytes), "text/csv")}
    upload_resp = client.post("/api/v1/datasets/", headers=auth_headers_user_a, files=files)
    dataset_id = upload_resp.json()["id"]
    process_dataset_background(dataset_id)

    mock_completion = MagicMock()
    mock_completion.choices = [
        MagicMock(
            message=MagicMock(
                content="""{
                    "suggestions": [
                        {"question": "Top cities?", "sql": "SELECT city, COUNT(*) FROM bakery_sales GROUP BY city;", "rationale": "City volume."},
                        {"question": "Average price?", "sql": "SELECT AVG(price) FROM bakery_sales;", "rationale": "Mean price."},
                        {"question": "Highest quantity?", "sql": "SELECT MAX(quantity) FROM bakery_sales;", "rationale": "Max units."},
                        {"question": "Missing quantities?", "sql": "SELECT * FROM bakery_sales WHERE quantity IS NULL;", "rationale": "Null check."},
                        {"question": "Sales by date?", "sql": "SELECT date, COUNT(*) FROM bakery_sales GROUP BY date;", "rationale": "Time trend."}
                    ]
                }"""
            )
        )
    ]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    with patch.object(settings, "GROQ_API_KEY", "gsk_test_mock_key_12345"):
        with patch("groq.Groq", return_value=mock_client):
            response = client.post(f"/api/v1/datasets/{dataset_id}/suggestions/", headers=auth_headers_user_a)
            assert response.status_code == 200
            data = response.json()
            assert len(data["suggestions"]) == 5

            # Inspect call arguments to verify privacy preservation
            mock_client.chat.completions.create.assert_called_once()
            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            messages = call_kwargs["messages"]
            sent_content = "".join(m["content"] for m in messages)

            # Metadata should be present
            assert "table_name" in sent_content
            assert "data_type" in sent_content

            # Raw cell records MUST NOT be present
            assert "Croissant" not in sent_content
            assert "Baguette" not in sent_content
            assert "Muffin" not in sent_content
            assert "Sourdough" not in sent_content
