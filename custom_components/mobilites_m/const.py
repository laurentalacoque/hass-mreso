"""Constants for the Mobilités M integration."""

DOMAIN = "mobilites_m"

API_BASE_URL = "https://data.mobilites-m.fr/api/routers/default/index"
API_HEADERS = {
    "Origin": "https://www.mobilites-m.fr",
    "Accept": "application/json",
}

CONF_ROUTE_ID = "route_id"
CONF_ROUTE_SHORT_NAME = "route_short_name"
CONF_ROUTE_COLOR = "route_color"
CONF_ROUTE_TEXT_COLOR = "route_text_color"
CONF_STOP_ID = "stop_id"
CONF_STOP_NAME = "stop_name"
CONF_DIRECTION_DIR = "direction_dir"
CONF_DESTINATION_NAME = "destination_name"
CONF_DEST_STOP_ID = "dest_stop_id"
CONF_DEST_STOP_NAME = "dest_stop_name"
CONF_ADD_ROUNDTRIP = "add_roundtrip"

UPDATE_INTERVAL_SECONDS = 60
DEPARTURE_MARGIN_SEC = 30
MAX_PASSAGES = 6