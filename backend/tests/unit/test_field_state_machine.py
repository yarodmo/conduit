"""
Conduit Tests — Field state machine + geofencing unit tests (M6).

Pure logic tests: no DB, no HTTP.

Bliss Systems LLC — APEX Standard
"""

import pytest
from app.models.field import ZoneStatus, ZONE_TRANSITIONS
from app.modules.field.service import _point_in_geofence


# ══════════════════════════════════════
# ZONE STATE MACHINE
# ══════════════════════════════════════

def test_not_started_can_only_go_in_progress():
    allowed = ZONE_TRANSITIONS[ZoneStatus.NOT_STARTED]
    assert ZoneStatus.IN_PROGRESS in allowed
    assert ZoneStatus.COMPLETED not in allowed
    assert ZoneStatus.BLOCKED not in allowed


def test_in_progress_can_complete_or_block():
    allowed = ZONE_TRANSITIONS[ZoneStatus.IN_PROGRESS]
    assert ZoneStatus.COMPLETED in allowed
    assert ZoneStatus.BLOCKED in allowed
    assert ZoneStatus.NOT_STARTED not in allowed


def test_blocked_can_only_go_in_progress():
    allowed = ZONE_TRANSITIONS[ZoneStatus.BLOCKED]
    assert ZoneStatus.IN_PROGRESS in allowed
    assert ZoneStatus.COMPLETED not in allowed


def test_completed_has_no_transitions():
    assert ZONE_TRANSITIONS[ZoneStatus.COMPLETED] == set()


def test_all_statuses_covered():
    for status in ZoneStatus:
        assert status in ZONE_TRANSITIONS, f"{status} missing from ZONE_TRANSITIONS"


# ══════════════════════════════════════
# GEOFENCING — RAY CASTING
# ══════════════════════════════════════

SQUARE_GEOFENCE = {
    "coordinates": [
        [-80.200, 25.700],   # SW
        [-80.200, 25.800],   # NW
        [-80.100, 25.800],   # NE
        [-80.100, 25.700],   # SE
        [-80.200, 25.700],   # close polygon
    ]
}


def test_point_inside_square():
    assert _point_in_geofence(25.750, -80.150, SQUARE_GEOFENCE) is True


def test_point_outside_square():
    assert _point_in_geofence(25.900, -80.150, SQUARE_GEOFENCE) is False


def test_point_outside_square_lng():
    assert _point_in_geofence(25.750, -79.999, SQUARE_GEOFENCE) is False


def test_empty_geofence_always_passes():
    assert _point_in_geofence(0.0, 0.0, {}) is True
    assert _point_in_geofence(99.9, -120.0, {"coordinates": []}) is True


def test_degenerate_geofence_two_points():
    geofence = {"coordinates": [[-80.1, 25.7], [-80.2, 25.8]]}
    # Less than 3 points → always True (no valid polygon)
    assert _point_in_geofence(25.750, -80.150, geofence) is True


def test_point_on_boundary_near_edge():
    # Very close to northern edge lat=25.8 — outside
    assert _point_in_geofence(25.801, -80.150, SQUARE_GEOFENCE) is False
