import os

os.environ["DATABASE_URL"] = "sqlite:///test.db"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
os.environ["TEXT_GENERATOR_PROVIDER"] = "template"
os.environ["PUBLIC_BASE_URL"] = "http://localhost:8080"

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
    os.remove("test.db")


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///test.db")
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()
