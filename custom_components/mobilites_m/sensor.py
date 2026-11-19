"""Sensor platform for Mobilités M."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MobilitesMStopCoordinator
from .const import (
    CONF_DEST_STOP_ID,
    CONF_DESTINATION_NAME,
    CONF_DIRECTION_DIR,
    CONF_ROUTE_COLOR,
    CONF_ROUTE_ID,
    CONF_ROUTE_SHORT_NAME,
    CONF_ROUTE_TEXT_COLOR,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    DEPARTURE_MARGIN_SEC,
    DOMAIN,
    MAX_PASSAGES,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mobilités M sensor from a config entry."""
    stop_id: str = entry.data[CONF_STOP_ID]
    coordinator: MobilitesMStopCoordinator = hass.data[DOMAIN]["coordinators"][stop_id]
    async_add_entities([MobilitesMPassageSensor(coordinator, entry)])


class MobilitesMPassageSensor(CoordinatorEntity[MobilitesMStopCoordinator], SensorEntity):
    """Sensor representing upcoming departures & arrivals for a line at a stop."""

    _attr_icon = "mdi:bus-clock"

    def __init__(self, coordinator: MobilitesMStopCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._route_id: str = entry.data[CONF_ROUTE_ID]
        self._short_name: str = entry.data[CONF_ROUTE_SHORT_NAME]
        self._stop_id: str = entry.data[CONF_STOP_ID]
        self._stop_name: str = entry.data[CONF_STOP_NAME]
        self._dir: int = entry.data[CONF_DIRECTION_DIR]
        self._dest_name: str = entry.data[CONF_DESTINATION_NAME]

        raw_dest_ids = entry.data.get(CONF_DEST_STOP_ID, [])
        if isinstance(raw_dest_ids, str):
            self._dest_stop_ids = {raw_dest_ids} if raw_dest_ids else set()
        else:
            self._dest_stop_ids = set(raw_dest_ids)

        self._attr_unique_id = f"{DOMAIN}_{self._route_id}_{self._stop_id}_{self._dir}"
        self._attr_name = f"{self._short_name} {self._stop_name} → {self._dest_name}"

    def _resolve_arrival(
        self, trip_id: str, dep_ts: int, arrivals_map: dict[str, list[dict]]
    ) -> tuple[int | None, str | None]:
        candidates = arrivals_map.get(trip_id, [])
        if not candidates:
            return None, None

        # Filtre sur les quais de destination configurés (si précisés) et vérifie arr_ts >= dep_ts
        valid = [
            c["arr_ts"]
            for c in candidates
            if c["arr_ts"] >= dep_ts
            and (not self._dest_stop_ids or c["stop_id"] in self._dest_stop_ids)
        ]
        if not valid:
            valid = [c["arr_ts"] for c in candidates if c["arr_ts"] >= dep_ts]

        if not valid:
            return None, None

        arr_ts = min(valid)
        arrival_time = datetime.fromtimestamp(arr_ts).astimezone().strftime("%H:%M")
        return arr_ts, arrival_time

    def _get_upcoming_passages(self) -> list[dict[str, Any]]:
        if not self.coordinator.data:
            return []

        now_ts: float = self.coordinator.data["now_ts"]
        patterns: list[dict] = self.coordinator.data["patterns"]
        arrivals_map: dict[str, list[dict]] = self.coordinator.data.get("arrivals_by_trip", {})
        passages: list[dict[str, Any]] = []

        for item in patterns:
            pat = item.get("pattern", {})
            pat_id = pat.get("id", "")
            pat_dir = pat.get("dir")

            if not pat_id.startswith(f"{self._route_id}:"):
                continue
            if pat_dir is not None and pat_dir != self._dir:
                continue

            for t in item.get("times", []):
                service_day = t.get("serviceDay", 0)
                sched_dep = t.get("scheduledDeparture", 0)
                real_dep = t.get("realtimeDeparture", sched_dep)
                is_realtime = bool(t.get("realtime", False))
                trip_id = t.get("tripId", "")

                dep_ts = int(service_day + real_dep)
                if dep_ts < (now_ts - DEPARTURE_MARGIN_SEC):
                    continue

                wait_min = max(0, round((dep_ts - now_ts) / 60))
                delay_min = round((real_dep - sched_dep) / 60)
                arr_ts, arrival_time = self._resolve_arrival(trip_id, dep_ts, arrivals_map)

                passages.append({
                    "dep_ts": dep_ts,
                    "arr_ts": arr_ts,
                    "departure_time": datetime.fromtimestamp(dep_ts).astimezone().strftime("%H:%M"),
                    "arrival_time": arrival_time,
                    "scheduled_time": datetime.fromtimestamp(service_day + sched_dep).astimezone().strftime("%H:%M"),
                    "wait_minutes": wait_min,
                    "delay_minutes": delay_min,
                    "realtime": is_realtime,
                    "headsign": t.get("headsign") or self._dest_name,
                    "trip_id": trip_id,
                })

        passages.sort(key=lambda p: p["dep_ts"])
        return passages[:MAX_PASSAGES]

    @property
    def native_value(self) -> str:
        passages = self._get_upcoming_passages()
        if not passages:
            return "Aucun passage"
        return passages[0]["departure_time"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        passages = self._get_upcoming_passages()
        next_bus = passages[0] if passages else {}
        return {
            "line": self._short_name,
            "route_id": self._route_id,
            "line_color": f"#{self._entry.data.get(CONF_ROUTE_COLOR, '0055A4')}",
            "line_text_color": f"#{self._entry.data.get(CONF_ROUTE_TEXT_COLOR, 'FFFFFF')}",
            "stop_id": self._stop_id,
            "stop_name": self._stop_name,
            "destination": self._dest_name,
            "next_wait_minutes": next_bus.get("wait_minutes"),
            "arrival_time": next_bus.get("arrival_time"),
            "arr_ts": next_bus.get("arr_ts"),
            "next_realtime": next_bus.get("realtime"),
            "next_delay_minutes": next_bus.get("delay_minutes"),
            "passages": passages,
            "downloaded_at": self.coordinator.data.get("downloaded_at") if self.coordinator.data else None,
        }