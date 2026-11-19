"""The Mobilités M integration."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from pathlib import Path
import time

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_BASE_URL,
    API_HEADERS,
    CONF_DEST_STOP_ID,
    CONF_STOP_ID,
    DOMAIN,
    UPDATE_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR]
FRONTEND_SCRIPT_BASE_URL = "/mobilites_m_static/mobilites-m-card.js"


class MobilitesMStopCoordinator(DataUpdateCoordinator):
    """Coordinator fetching real-time stoptimes for origin and destination stops."""

    def __init__(self, hass: HomeAssistant, stop_id: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{stop_id}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.stop_id = stop_id
        self.dest_stop_ids: set[str] = set()
        self.session = async_get_clientsession(hass)

    def register_destinations(self, dest_ids: list[str] | set[str]) -> None:
        """Register destination physical stop_ids to poll alongside origin."""
        for did in dest_ids:
            if did and did != self.stop_id:
                self.dest_stop_ids.add(did)

    async def _fetch_stop_stoptimes(self, target_stop_id: str, date_str: str) -> tuple[str, list]:
        url = f"{API_BASE_URL}/stops/{target_stop_id}/stoptimes/{date_str}"
        async with self.session.get(url, headers=API_HEADERS, timeout=15) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return target_stop_id, (data if isinstance(data, list) else [])

    async def _async_update_data(self) -> dict:
        date_str = datetime.now().strftime("%Y%m%d")

        try:
            _, origin_patterns = await self._fetch_stop_stoptimes(self.stop_id, date_str)
        except Exception as err:
            raise UpdateFailed(f"Error fetching Mobilités M stoptimes for {self.stop_id}: {err}") from err

        # Si aucune destination explicite n'a été enregistrée (ancienne entrée),
        # on récupère les terminus (lastStop) détectés dans les patterns
        targets = set(self.dest_stop_ids)
        if not targets:
            for item in origin_patterns:
                last_stop = item.get("pattern", {}).get("lastStop")
                if last_stop and last_stop != self.stop_id:
                    targets.add(last_stop)

        # Interroge les quais de destination en parallèle et indexe par tripId
        arrivals_by_trip: dict[str, list[dict]] = {}
        if targets:
            results = await asyncio.gather(
                *(self._fetch_stop_stoptimes(did, date_str) for did in targets),
                return_exceptions=True,
            )
            for res in results:
                if isinstance(res, tuple):
                    dest_id, patterns = res
                    for item in patterns:
                        for t in item.get("times", []):
                            trip_id = t.get("tripId")
                            if not trip_id:
                                continue
                            service_day = t.get("serviceDay", 0)
                            arr_sec = t.get("realtimeArrival")
                            if arr_sec is None:
                                arr_sec = t.get("scheduledArrival")
                            if service_day and arr_sec is not None:
                                arrivals_by_trip.setdefault(trip_id, []).append({
                                    "stop_id": dest_id,
                                    "arr_ts": int(service_day + arr_sec),
                                })

        return {
            "patterns": origin_patterns,
            "arrivals_by_trip": arrivals_by_trip,
            "now_ts": time.time(),
            "downloaded_at": datetime.now().astimezone().isoformat(),
        }


async def _ensure_frontend_registered(hass: HomeAssistant) -> None:
    """Register static path and versioned Lovelace JS module once."""
    hass.data.setdefault(DOMAIN, {})
    if not hass.data[DOMAIN].get("frontend_loaded"):
        hass.data[DOMAIN]["frontend_loaded"] = True
        js_path = Path(__file__).parent / "frontend" / "mobilites-m-card.js"
        if js_path.exists():
            try:
                await hass.http.async_register_static_paths([
                    StaticPathConfig(FRONTEND_SCRIPT_BASE_URL, str(js_path), cache_headers=False)
                ])
            except RuntimeError:
                pass
            version = int(js_path.stat().st_mtime)
            add_extra_js_url(hass, f"{FRONTEND_SCRIPT_BASE_URL}?v={version}")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register static frontend path at startup."""
    await _ensure_frontend_registered(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mobilités M from a config entry."""
    await _ensure_frontend_registered(hass)
    hass.data[DOMAIN].setdefault("coordinators", {})
    hass.data[DOMAIN].setdefault("locks", {})

    stop_id: str = entry.data[CONF_STOP_ID]
    if stop_id not in hass.data[DOMAIN]["coordinators"]:
        hass.data[DOMAIN]["coordinators"][stop_id] = MobilitesMStopCoordinator(hass, stop_id)
        hass.data[DOMAIN]["locks"][stop_id] = asyncio.Lock()

    coordinator: MobilitesMStopCoordinator = hass.data[DOMAIN]["coordinators"][stop_id]

    raw_dests = entry.data.get(CONF_DEST_STOP_ID, [])
    dest_list = [raw_dests] if isinstance(raw_dests, str) else list(raw_dests)
    coordinator.register_destinations(dest_list)

    async with hass.data[DOMAIN]["locks"][stop_id]:
        if coordinator.data is None:
            await coordinator.async_refresh()
            if not coordinator.last_update_success:
                raise ConfigEntryNotReady(f"Initial fetch failed: {coordinator.last_exception}")
        else:
            await coordinator.async_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    stop_id: str = entry.data[CONF_STOP_ID]

    remaining = [
        e for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id
        and e.data.get(CONF_STOP_ID) == stop_id
        and e.state.recoverable
    ]
    if unload_ok and not remaining:
        hass.data[DOMAIN]["coordinators"].pop(stop_id, None)
        hass.data[DOMAIN]["locks"].pop(stop_id, None)

    return unload_ok