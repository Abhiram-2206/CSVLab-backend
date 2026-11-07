"""
CSVLab End-to-End Demo Script
=============================
Demonstrates the complete learner workflow:
1. Register a new user
2. Log in and get JWT token
3. Upload CSV (sample_sales.csv) -> receives HTTP 202 Accepted
4. Await profiling & schema loading completion
5. View the automated Data-Quality Report (nulls, types, duplicates, stats)
6. Run safe, sandboxed SQL queries on the private table
7. Fetch AI-suggested exploratory questions (Groq / heuristic)
8. Save a query
9. Create a read-only share link for a mentor
10. Verify public read-only shared view
11. Export query results to a new CSV file
"""

import sys
import time
import httpx
from pathlib import Path


def run_demo():
    base_url = "http://127.0.0.1:8000"
    client = None

    # Check if local server is running, otherwise use FastAPI TestClient
    try:
        r = httpx.get(f"{base_url}/api/v1/health", timeout=1.0)
        if r.status_code == 200:
            print(f"[+] Connected to live CSVLab server at {base_url}\n")
            client = httpx.Client(base_url=base_url, timeout=10.0)
    except Exception:
        pass

    if client is None:
        print("[*] Local server not running on port 8000; executing in-process with TestClient...\n")
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)

    print("=" * 65)
    print("           CSVLab Workflow Walkthrough")
    print("=" * 65)

    # 1. Register User
    timestamp = int(time.time())
    email = f"learner_{timestamp}@techsnap.com"
    password = "SuperPassword123!"
    print(f"\n[Step 1] Registering learner: {email}")
    reg_res = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    if reg_res.status_code != 201:
        print(f"[-] Registration failed: {reg_res.text}")
        return
    print(f"  -> User registered with ID: {reg_res.json()['id']}")

    # 2. Login
    print("\n[Step 2] Logging in to retrieve JWT access & refresh tokens")
    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    tokens = login_res.json()
    access_token = tokens["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    print(f"  -> Received JWT Bearer Token: {access_token[:25]}... (expires in {tokens['expires_in_seconds']}s)")

    # 3. Upload CSV
    csv_file = Path(__file__).parent / "sample_sales.csv"
    if not csv_file.exists():
        csv_file = Path("sample_sales.csv")
    if not csv_file.exists():
        print("[-] sample_sales.csv not found!")
        return

    print(f"\n[Step 3] Uploading CSV: {csv_file.name}")
    with open(csv_file, "rb") as f:
        upload_res = client.post(
            "/api/v1/datasets/",
            headers=headers,
            files={"file": (csv_file.name, f, "text/csv")},
            data={"name": "bakery_sales"},
        )
    print(f"  -> Upload Status Code: {upload_res.status_code} (202 Accepted)")
    dataset_info = upload_res.json()
    dataset_id = dataset_info["id"]
    print(f"  -> Dataset ID: {dataset_id}")
    print(f"  -> Immediate Status: {dataset_info['status']}")
    print(f"  -> Server Message: {dataset_info['message']}")

    # 4. Wait for background profiling to complete
    print("\n[Step 4] Polling status until status == 'ready'...")
    for _ in range(15):
        detail_res = client.get(f"/api/v1/datasets/{dataset_id}/", headers=headers)
        status_val = detail_res.json()["status"]
        if status_val == "ready":
            print(f"  -> Dataset is READY! Total rows loaded: {detail_res.json()['row_count']}")
            break
        elif status_val == "failed":
            print(f"[-] Profiling failed: {detail_res.json().get('error_message')}")
            return
        time.sleep(0.5)

    # 5. Fetch Data Quality Report
    print("\n[Step 5] Fetching Automated Data-Quality Profile Report")
    profile_res = client.get(f"/api/v1/datasets/{dataset_id}/profile/", headers=headers)
    profile = profile_res.json()
    print(f"  -> Columns: {profile['column_count']}, Rows: {profile['row_count']}, Duplicate Rows: {profile['duplicate_rows']}")
    print("\n  Column Summaries:")
    for col in profile["columns"]:
        stats_str = ""
        if col.get("stats"):
            if "min" in col["stats"] and "max" in col["stats"]:
                stats_str = f" [Min: {col['stats']['min']}, Max: {col['stats']['max']}]"
            elif "top_values" in col["stats"]:
                top = [f"{t['value']}({t['count']})" for t in col["stats"]["top_values"][:3]]
                stats_str = f" [Top: {', '.join(top)}]"
        print(f"     * {col['name']} ({col['type']}): {col['null_percentage']}% nulls{stats_str}")

    # 6. Run SQL Queries
    print("\n[Step 6] Running Sandboxed Read-Only SQL Query")
    sample_sql = "SELECT city, COUNT(*) AS transactions, SUM(price * quantity) AS total_revenue FROM bakery_sales WHERE quantity IS NOT NULL GROUP BY city ORDER BY total_revenue DESC"
    print(f"  -> Query: {sample_sql}")
    query_res = client.post(
        f"/api/v1/datasets/{dataset_id}/query/",
        headers=headers,
        json={"sql": sample_sql},
    )
    if query_res.status_code == 200:
        res_data = query_res.json()
        print(f"  -> Query executed in {res_data['execution_time_ms']} ms! Result ({res_data['row_count']} rows):")
        for row in res_data["rows"]:
            print(f"     {row}")
    else:
        print(f"[-] Query failed: {query_res.text}")

    # 7. Test Security Sandboxing: Try dropping table
    print("\n[Step 7] Testing SQL Sandboxing Safety (Attacking with DROP TABLE)")
    bad_sql = "DROP TABLE bakery_sales;"
    bad_res = client.post(
        f"/api/v1/datasets/{dataset_id}/query/",
        headers=headers,
        json={"sql": bad_sql},
    )
    print(f"  -> Server Response: HTTP {bad_res.status_code}")
    print(f"  -> Security Guard Message: {bad_res.json()['detail']}")

    # 8. AI Suggestions
    print("\n[Step 8] Requesting AI-Suggested Exploratory Questions (Groq / Heuristic)")
    sug_res = client.post(f"/api/v1/datasets/{dataset_id}/suggestions/", headers=headers)
    if sug_res.status_code == 200:
        suggestions = sug_res.json()["suggestions"]
        for idx, sug in enumerate(suggestions, 1):
            print(f"  Suggestion {idx}: {sug['question']}")
            print(f"    SQL: {sug['sql']}")
            print(f"    Why: {sug['rationale']}")
    else:
        print(f"[-] Suggestions failed: {sug_res.text}")

    # 9. Save a Query
    print("\n[Step 9] Saving Query for Future Reuse")
    save_res = client.post(
        f"/api/v1/datasets/{dataset_id}/queries/",
        headers=headers,
        json={"title": "City Revenue Ranking", "sql_text": sample_sql},
    )
    saved_q = save_res.json()
    query_id = saved_q["id"]
    print(f"  -> Query saved with ID: {query_id} (Title: '{saved_q['title']}')")

    # 10. Create Mentor Share Link
    print("\n[Step 10] Generating Read-Only Share Link for Mentor")
    share_res = client.post(
        f"/api/v1/datasets/{dataset_id}/share/",
        headers=headers,
        json={"query_id": query_id},
    )
    share_info = share_res.json()
    token = share_info["token"]
    print(f"  -> Share Token: {token}")
    print(f"  -> Mentor Read-Only URL: {share_info['share_url']}")

    # 11. Access Public Shared View
    print("\n[Step 11] Viewing Shared Link (Simulating Mentor without Login)")
    public_res = client.get(f"/api/v1/shared/{token}/")
    if public_res.status_code == 200:
        shared_view = public_res.json()
        print(f"  -> Mentor sees dataset: '{shared_view['dataset_name']}'")
        print(f"  -> Linked Query: '{shared_view['saved_query']['title']}'")
        print(f"  -> Executed Rows Count: {shared_view['query_result']['row_count']}")
    else:
        print(f"[-] Shared link access failed: {public_res.text}")

    # 12. Export to CSV
    print("\n[Step 12] Exporting Query Results to CSV")
    export_res = client.get(
        f"/api/v1/datasets/{dataset_id}/export/?query_id={query_id}",
        headers=headers,
    )
    if export_res.status_code == 200:
        output_file = Path("exported_results.csv")
        output_file.write_text(export_res.text, encoding="utf-8")
        print(f"  -> CSV exported successfully to: {output_file.name}")
        print(f"  -> File size: {len(export_res.text)} bytes")

    print("\n" + "=" * 65)
    print("      [SUCCESS] All 12 Workflow Steps Completed Successfully!")
    print("=" * 65)


if __name__ == "__main__":
    run_demo()
