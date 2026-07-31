"""Deterministic fake flight controller for testing."""
from __future__ import annotations

from drone.interfaces import Pose


class FakeFlightController:
    """Simple kinematic fake FC — moves toward targets at fixed speed."""

    SPEED: float = 5.0        # m/s horizontal
    VERTICAL_SPEED: float = 2.0  # m/s vertical
    BATTERY_DRAIN: float = 0.0001  # per step while armed

    def __init__(self) -> None:
        self._pose = Pose(x=0.0, y=0.0, z=0.0, heading=0.0)
        self._armed: bool = False
        self._target_x: float = 0.0
        self._target_y: float = 0.0
        self._target_z: float = 0.0
        self._landing: bool = False
        self._battery: float = 1.0

    def arm(self) -> None:
        self._armed = True

    def takeoff(self, altitude: float) -> None:
        if not self._armed:
            raise RuntimeError("Cannot take off — not armed")
        self._target_z = altitude

    def land(self) -> None:
        self._landing = True
        self._target_z = 0.0

    def goto(self, x: float, y: float, z: float) -> None:
        self._target_x = x
        self._target_y = y
        self._target_z = z
        self._landing = False

    def step(self, dt: float) -> None:
        if not self._armed:
            return

        # Move toward target
        dx = self._target_x - self._pose.x
        dy = self._target_y - self._pose.y
        dz = self._target_z - self._pose.z

        h_dist = (dx * dx + dy * dy) ** 0.5
        if h_dist > 0.01:
            move = min(self.SPEED * dt, h_dist)
            self._pose = Pose(
                x=self._pose.x + dx / h_dist * move,
                y=self._pose.y + dy / h_dist * move,
                z=self._pose.z,
                heading=self._pose.heading,
            )

        dz = self._target_z - self._pose.z
        if abs(dz) > 0.01:
            move = min(self.VERTICAL_SPEED * dt, abs(dz))
            self._pose = Pose(
                x=self._pose.x,
                y=self._pose.y,
                z=self._pose.z + move * (1 if dz > 0 else -1),
                heading=self._pose.heading,
            )

        # Battery drain
        if self._armed:
            self._battery = max(0.0, self._battery - self.BATTERY_DRAIN)

    def get_pose(self) -> Pose:
        return self._pose

    def get_battery(self) -> float:
        return self._battery

    def is_armed(self) -> bool:
        return self._armed
