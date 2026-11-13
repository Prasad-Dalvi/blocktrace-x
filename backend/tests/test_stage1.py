import pytest
from app import create_app, db
from app.models import Role, User, Supplier, SupplierLot, ProductionBatch


@pytest.fixture
def client():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.app_context():
        r_admin = Role(name="Admin")
        r_mfg = Role(name="Manufacturer")
        db.session.add_all([r_admin, r_mfg])
        db.session.flush()

        u = User(email="mfg@test.io", full_name="Test Mfg", role_id=r_mfg.id)
        u.set_password("Secret123")
        db.session.add(u)

        sup = Supplier(code="S03", name="Supplier S03", material_category="Adhesive")
        db.session.add(sup)
        db.session.flush()

        lot = SupplierLot(
            lot_code="LOT-2023-114",
            supplier_id=sup.id,
            material_name="Adhesive",
            quantity_received=1000.0,
        )
        b1 = ProductionBatch(batch_code="2023-0101", machine_id="MC-04", units_produced=502, qc_status="FAIL")
        b2 = ProductionBatch(batch_code="2023-0459", machine_id="MC-03", units_produced=367, qc_status="FAIL")
        db.session.add_all([lot, b1, b2])
        db.session.commit()

    with app.test_client() as client:
        yield client


def _get_token(client):
    res = client.post("/api/auth/login", json={"email": "mfg@test.io", "password": "Secret123"})
    return res.get_json()["access_token"]


def test_auth_and_multi_parent_dag_validation(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    r1 = client.post(
        "/api/manufacturing/relations",
        json={
            "parent_type": "LOT",
            "parent_code": "LOT-2023-114",
            "child_type": "BATCH",
            "child_code": "2023-0101",
            "quantity_consumed": 50.0,
        },
        headers=headers,
    )
    assert r1.status_code == 201

    r_dup = client.post(
        "/api/manufacturing/relations",
        json={
            "parent_type": "LOT",
            "parent_code": "LOT-2023-114",
            "child_type": "BATCH",
            "child_code": "2023-0101",
            "quantity_consumed": 50.0,
        },
        headers=headers,
    )
    assert r_dup.status_code == 400

    r2 = client.post(
        "/api/manufacturing/relations",
        json={
            "parent_type": "BATCH",
            "parent_code": "2023-0101",
            "child_type": "BATCH",
            "child_code": "2023-0459",
            "quantity_consumed": 100.0,
        },
        headers=headers,
    )
    assert r2.status_code == 201

    r_cycle = client.post(
        "/api/manufacturing/relations",
        json={
            "parent_type": "BATCH",
            "parent_code": "2023-0459",
            "child_type": "BATCH",
            "child_code": "2023-0101",
            "quantity_consumed": 100.0,
        },
        headers=headers,
    )
    assert r_cycle.status_code == 400
    assert "Cycle detected" in r_cycle.get_json()["error"]
