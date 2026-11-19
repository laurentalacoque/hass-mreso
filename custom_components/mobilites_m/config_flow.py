"""Config flow for Mobilités M integration."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    API_BASE_URL,
    API_HEADERS,
    CONF_ADD_ROUNDTRIP,
    CONF_DEST_STOP_ID,
    CONF_DEST_STOP_NAME,
    CONF_DESTINATION_NAME,
    CONF_DIRECTION_DIR,
    CONF_ROUTE_COLOR,
    CONF_ROUTE_ID,
    CONF_ROUTE_SHORT_NAME,
    CONF_ROUTE_TEXT_COLOR,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    DOMAIN,
)


class MobilitesMConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mobilités M."""

    VERSION = 1

    def __init__(self) -> None:
        self._routes: dict[str, dict] = {}
        self._selected_route: dict[str, Any] = {}
        self._stops_by_name: dict[str, list[dict]] = {}
        self._selected_stop_name: str = ""
        self._directions: dict[str, dict] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 1: Select the bus/tram line."""
        errors: dict[str, str] = {}

        if not self._routes:
            session = async_get_clientsession(self.hass)
            try:
                async with session.get(
                    f"{API_BASE_URL}/routes", headers=API_HEADERS, timeout=15
                ) as resp:
                    resp.raise_for_status()
                    routes_list = await resp.json()

                routes_list.sort(
                    key=lambda r: (
                        0 if r.get("id", "").startswith("SEM:") else 1,
                        r.get("shortName", ""),
                    )
                )
                for r in routes_list:
                    rid = r.get("id")
                    if rid:
                        self._routes[rid] = r
            except Exception:
                errors["base"] = "cannot_connect"

        if user_input is not None and not errors:
            route_id = user_input[CONF_ROUTE_ID]
            self._selected_route = self._routes[route_id]
            return await self.async_step_stop()

        options = [
            SelectOptionDict(
                value=rid,
                label=f"{r.get('shortName', rid)} — {r.get('longName', '')}",
            )
            for rid, r in self._routes.items()
        ]

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_ROUTE_ID): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                )
            }),
            errors=errors,
        )

    async def async_step_stop(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 2: Select the departure stop name on this line."""
        errors: dict[str, str] = {}
        route_id = self._selected_route["id"]

        if not self._stops_by_name:
            session = async_get_clientsession(self.hass)
            try:
                async with session.get(
                    f"{API_BASE_URL}/routes/{route_id}/stops",
                    headers=API_HEADERS,
                    timeout=15,
                ) as resp:
                    resp.raise_for_status()
                    stops_list = await resp.json()

                grouped: dict[str, list[dict]] = {}
                for stop in stops_list:
                    name = stop.get("name", "").strip()
                    if name:
                        grouped.setdefault(name, []).append(stop)
                self._stops_by_name = dict(sorted(grouped.items()))
            except Exception:
                errors["base"] = "cannot_connect"

        if user_input is not None and not errors:
            self._selected_stop_name = user_input[CONF_STOP_NAME]
            return await self.async_step_direction()

        options = [
            SelectOptionDict(value=name, label=name)
            for name in self._stops_by_name
        ]

        return self.async_show_form(
            step_id="stop",
            data_schema=vol.Schema({
                vol.Required(CONF_STOP_NAME): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                )
            }),
            errors=errors,
        )

    async def async_step_direction(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 3: Select direction & optional arrival stop."""
        errors: dict[str, str] = {}
        route_id = self._selected_route["id"]
        short_name = self._selected_route.get("shortName", route_id)
        candidate_stops = self._stops_by_name.get(self._selected_stop_name, [])

        if not self._directions:
            session = async_get_clientsession(self.hass)
            date_str = datetime.now().strftime("%Y%m%d")

            for stop in candidate_stops:
                stop_id = stop["id"]
                try:
                    async with session.get(
                        f"{API_BASE_URL}/stops/{stop_id}/stoptimes/{date_str}",
                        headers=API_HEADERS,
                        timeout=15,
                    ) as resp:
                        resp.raise_for_status()
                        patterns_data = await resp.json()

                    for item in patterns_data:
                        pat = item.get("pattern", {})
                        pat_id = pat.get("id", "")
                        if pat_id.startswith(f"{route_id}:"):
                            dir_num = pat.get("dir", 0)
                            dest_name = pat.get("lastStopName") or pat.get("desc") or f"Direction {dir_num}"
                            last_stop_id = pat.get("lastStop", "")
                            key = f"{stop_id}|{dir_num}"
                            if key not in self._directions:
                                self._directions[key] = {
                                    "stop_id": stop_id,
                                    "dir": dir_num,
                                    "dest_name": dest_name,
                                    "last_stop_id": last_stop_id,
                                }
                except Exception:
                    continue

            if not self._directions:
                for idx, stop in enumerate(candidate_stops):
                    key = f"{stop['id']}|{idx}"
                    self._directions[key] = {
                        "stop_id": stop["id"],
                        "dir": idx,
                        "dest_name": f"Quai {stop['id']}",
                        "last_stop_id": "",
                    }

        if user_input is not None:
            selected_key = user_input["direction_key"]
            chosen = self._directions[selected_key]
            dest_stop_name = user_input.get(CONF_DEST_STOP_NAME, "__TERMINUS__")
            add_roundtrip = user_input.get(CONF_ADD_ROUNDTRIP, False)

            if dest_stop_name and dest_stop_name != "__TERMINUS__":
                dest_candidates = [s["id"] for s in self._stops_by_name.get(dest_stop_name, [])]
                display_dest = dest_stop_name
            else:
                dest_candidates = [chosen["last_stop_id"]] if chosen["last_stop_id"] else []
                display_dest = chosen["dest_name"]

            base_data = {
                CONF_ROUTE_ID: route_id,
                CONF_ROUTE_SHORT_NAME: short_name,
                CONF_ROUTE_COLOR: self._selected_route.get("color", "0055A4"),
                CONF_ROUTE_TEXT_COLOR: self._selected_route.get("textColor", "FFFFFF"),
                CONF_STOP_ID: chosen["stop_id"],
                CONF_STOP_NAME: self._selected_stop_name,
                CONF_DIRECTION_DIR: chosen["dir"],
                CONF_DESTINATION_NAME: display_dest,
                CONF_DEST_STOP_ID: dest_candidates,
            }

            if add_roundtrip:
                other_keys = [k for k in self._directions if k != selected_key]
                if other_keys:
                    other = self._directions[other_keys[0]]
                    if dest_stop_name and dest_stop_name != "__TERMINUS__":
                        # Au retour, l'arrêt d'arrivée choisi devient l'arrêt de départ
                        rt_candidates = self._stops_by_name.get(dest_stop_name, [])
                        rt_stop_id = rt_candidates[0]["id"] if rt_candidates else other["stop_id"]
                        rt_origin_name = dest_stop_name
                        rt_dest_ids = [s["id"] for s in candidate_stops]
                        rt_dest_name = self._selected_stop_name
                    else:
                        rt_stop_id = other["stop_id"]
                        rt_origin_name = self._selected_stop_name
                        rt_dest_ids = [other["last_stop_id"]] if other["last_stop_id"] else []
                        rt_dest_name = other["dest_name"]

                    return_data = {
                        **base_data,
                        CONF_STOP_ID: rt_stop_id,
                        CONF_STOP_NAME: rt_origin_name,
                        CONF_DIRECTION_DIR: other["dir"],
                        CONF_DESTINATION_NAME: rt_dest_name,
                        CONF_DEST_STOP_ID: rt_dest_ids,
                    }
                    self.hass.async_create_task(
                        self.hass.config_entries.flow.async_init(
                            DOMAIN,
                            context={"source": "roundtrip"},
                            data=return_data,
                        )
                    )

            title = f"{short_name} {self._selected_stop_name} → {display_dest}"
            return self.async_create_entry(title=title, data=base_data)

        dir_options = [
            SelectOptionDict(
                value=key,
                label=f"Vers {info['dest_name']} ({info['stop_id']})",
            )
            for key, info in self._directions.items()
        ]

        arrival_options = [
            SelectOptionDict(value="__TERMINUS__", label="Terminus de la direction (par défaut)")
        ] + [
            SelectOptionDict(value=name, label=name)
            for name in self._stops_by_name
            if name != self._selected_stop_name
        ]

        return self.async_show_form(
            step_id="direction",
            data_schema=vol.Schema({
                vol.Required("direction_key"): SelectSelector(
                    SelectSelectorConfig(options=dir_options, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Optional(CONF_DEST_STOP_NAME, default="__TERMINUS__"): SelectSelector(
                    SelectSelectorConfig(options=arrival_options, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Optional(CONF_ADD_ROUNDTRIP, default=False): bool,
            }),
            errors=errors,
        )

    async def async_step_roundtrip(
        self, data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Create the return trip entry automatically."""
        title = f"{data[CONF_ROUTE_SHORT_NAME]} {data[CONF_STOP_NAME]} → {data[CONF_DESTINATION_NAME]}"
        return self.async_create_entry(title=title, data=data)