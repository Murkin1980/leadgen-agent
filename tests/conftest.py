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
os.environ["OUTREACH_PROVIDER"] = "mock"
os.environ["OUTREACH_ENABLED"] = "false"
os.environ["OUTREACH_MAX_PER_HOUR"] = "20"
os.environ["OUTREACH_QUIET_HOURS_START"] = "20:00"
os.environ["OUTREACH_QUIET_HOURS_END"] = "09:00"
os.environ["OUTREACH_TIMEZONE"] = "Asia/Almaty"
os.environ["FOLLOW_UP_ENABLED"] = "true"
os.environ["FOLLOW_UP_DELAY_HOURS"] = "48"
os.environ["FOLLOW_UP_MAX_COUNT"] = "2"

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
