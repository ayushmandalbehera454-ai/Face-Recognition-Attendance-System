import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app          # noqa: E402
from extensions import db           # noqa: E402


@pytest.fixture()
def app():
    app = create_app("testing")
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_client(app, client):
    r = client.post("/login", data={"username": app.config["ADMIN_USERNAME"],
                                    "password": app.config["ADMIN_PASSWORD"]})
    assert r.status_code == 302
    return client
