import io
import os
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import app.database as app_db
from app.main import app
from app.database import Base, get_db
from app.config import settings

# Test database file
TEST_DB_FILE = Path(__file__).parent / "test_suite.db"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_FILE}"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

@event.listens_for(test_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Patch app.database globally for test runs
app_db.engine = test_engine
app_db.SessionLocal = TestingSessionLocal
settings.DATABASE_URL = TEST_DATABASE_URL


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    # Use temporary upload directory for tests
    with tempfile.TemporaryDirectory() as temp_dir:
        original_upload_dir = settings.UPLOAD_DIR
        settings.UPLOAD_DIR = temp_dir
        yield
        settings.UPLOAD_DIR = original_upload_dir

    # Cleanup test db file after session
    test_engine.dispose()
    if TEST_DB_FILE.exists():
        try:
            TEST_DB_FILE.unlink()
        except Exception:
            pass


@pytest.fixture(autouse=True)
def clean_db():
    # Create tables
    Base.metadata.create_all(bind=test_engine)
    yield
    # Drop all tables after test
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def user_a_credentials():
    return {"email": "priya@example.com", "password": "Password123!"}


@pytest.fixture
def user_b_credentials():
    return {"email": "arjun@example.com", "password": "Password456!"}


@pytest.fixture
def auth_headers_user_a(client, user_a_credentials):
    # Register and login User A
    client.post("/api/v1/auth/register", json=user_a_credentials)
    resp = client.post("/api/v1/auth/login", json=user_a_credentials)
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_user_b(client, user_b_credentials):
    # Register and login User B
    client.post("/api/v1/auth/register", json=user_b_credentials)
    resp = client.post("/api/v1/auth/login", json=user_b_credentials)
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_csv_bytes():
    """
    Standard bakery_sales CSV from PRD:
    date, item, price, quantity, city
    Has known duplicates and missing values for profiling verification.
    """
    csv_data = (
        "date,item,price,quantity,city\n"
        "2026-01-01,Croissant,3.50,10,Bangalore\n"
        "2026-01-01,Baguette,2.00,15,Mumbai\n"
        "2026-01-02,Croissant,3.50,8,Bangalore\n"
        "2026-01-02,Muffin,2.50,20,Delhi\n"
        "2026-01-01,Croissant,3.50,10,Bangalore\n"  # Exact duplicate of line 1
        "2026-01-03,Sourdough,5.00,,Delhi\n"        # Missing quantity
    )
    return csv_data.encode("utf-8")
