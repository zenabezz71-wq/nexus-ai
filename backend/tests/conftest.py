import os
os.environ["DATABASE_URL"]="sqlite:///./test_nexus.db"
os.environ["JWT_SECRET"]="test-secret-long-enough-for-unit-tests"
from fastapi.testclient import TestClient
import pytest
from app.main import app
from app.database import Base,engine,SessionLocal
from app.models import Organization,User,Membership
from app.auth import hash_password
@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine);Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
@pytest.fixture
def client():
    with TestClient(app) as c:yield c
@pytest.fixture
def token(client):
    db=SessionLocal();o=Organization(name="Test",slug="test");u=User(email="test@example.com",password_hash=hash_password("StrongPass123!"))
    db.add_all([o,u]);db.flush();db.add(Membership(user_id=u.id,organization_id=o.id,role="owner"));db.commit();db.close()
    return client.post("/auth/login",json={"email":"test@example.com","password":"StrongPass123!"}).json()["access_token"]
