import os

os.environ["DATABASE_URL"] = "sqlite:///test.db"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
os.environ["TEXT_GENERATOR_PROVIDER"] = "mock"
os.environ["PUBLIC_BASE_URL"] = "http://localhost:8080"
os.environ["DEPLOYMENT_PROVIDER"] = "mock"
os.environ["COLLECTOR_PROVIDER"] = "mock"
os.environ["VERIFICATION_ENABLED"] = "false"
os.environ["LEAD_MIN_SCORE"] = "50"
os.environ["OPENAI_API_KEY"] = ""
os.environ["OPENAI_MODEL"] = "gpt-4o-mini"
os.environ["APP_ENV"] = "development"
os.environ["ADMIN_PASSWORD"] = "testpass"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    engine = create_engine("sqlite:///test.db")
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
    try:
        os.remove("test.db")
    except PermissionError:
        pass


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///test.db")
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()
