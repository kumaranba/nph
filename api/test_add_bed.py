"""Tests for adding a bed to a room with an auto-incremented label (addBed)."""
import pytest

from api.models import Bed, BedStatus, Room

ADD_BED = """
mutation($roomId: ID!) {
  addBed(roomId: $roomId) { id label status room { id name } }
}
"""


@pytest.fixture
def room(db):
    return Room.objects.create(name="MW1", capacity=2)


# --- next_label helper ----------------------------------------------------

def test_next_label_increments_highest(room):
    Bed.objects.create(room=room, label="B23")
    Bed.objects.create(room=room, label="B24")
    assert Bed.next_label(room) == "B25"


def test_next_label_empty_room_starts_at_b1(room):
    assert Bed.next_label(room) == "B1"


def test_next_label_keeps_prefix_and_ignores_non_numeric(room):
    Bed.objects.create(room=room, label="T7")
    Bed.objects.create(room=room, label="reserved")   # no number → ignored
    assert Bed.next_label(room) == "T8"


def test_next_label_is_unique_within_room(room):
    # Highest is B5 but B6 already exists (out-of-order) → skip to B7.
    Bed.objects.create(room=room, label="B5")
    Bed.objects.create(room=room, label="B6")
    assert Bed.next_label(room) == "B7"


# --- addBed mutation ------------------------------------------------------

def test_admin_adds_next_bed(admin_client, room):
    Bed.objects.create(room=room, label="B24", status=BedStatus.OCCUPIED)
    result = admin_client.execute(ADD_BED, {"roomId": str(room.id)})
    assert result.get("errors") is None
    data = result["data"]["addBed"]
    assert data["label"] == "B25"
    assert data["status"] == "VACANT"
    assert data["room"]["name"] == "MW1"
    assert Bed.objects.filter(room=room, label="B25").exists()


def test_add_bed_bumps_capacity_when_exceeded(admin_client, room):
    # capacity is 2; add three beds → capacity keeps up.
    for _ in range(3):
        admin_client.execute(ADD_BED, {"roomId": str(room.id)})
    room.refresh_from_db()
    assert room.beds.count() == 3
    assert room.capacity >= 3


def test_add_bed_unknown_room(admin_client):
    result = admin_client.execute(ADD_BED, {"roomId": "999999"})
    assert result["errors"]


@pytest.mark.parametrize("client_name", ["finance_client", "nurse_client", "pro_client"])
def test_add_bed_forbidden_for_non_admin(request, client_name, room):
    client = request.getfixturevalue(client_name)
    result = client.execute(ADD_BED, {"roomId": str(room.id)})
    assert result["errors"]
    assert room.beds.count() == 0
