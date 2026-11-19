# Mobilités M / M réso for Home Assistant (`hass-mreso`)

Custom Home Assistant integration to track real-time bus and tram schedules in the Grenoble metropolitan area (M réso / TAG / SMMAG network) via the `data.mobilites-m.fr` Open Data API, complete with a built-in Lovelace card.

## Features

- **Real-Time & Scheduled Departures**: Polls every 60 seconds with countdown in minutes and a live real-time indicator.
- **Automatic Arrival Time Calculation**: Matches `tripId` values between the origin stop and the destination stop (or line terminus).
- **3-Step UI Configuration (Config Flow)**: Select the line, origin stop, direction, and destination stop (with optional automatic round-trip creation).
- **Built-in Lovelace Card (`custom:mobilites-m-card`)**: Displays official line badge colors and automatically handles browser cache invalidation via versioning.

## Installation

1. In Home Assistant, go to **Settings > Marketplace**.
2. Open the menu in the top right corner (**⋮**) and select **Custom repositories** (or add `https://github.com/laurentalacoque/hass-mreso` as an **Integration**).
3. Search for **Mobilités M / M réso (TAG / SMMAG)**, click **Download / Install**, and restart Home Assistant.

## Configuration

1. Navigate to **Settings > Devices & services > Add integration**.
2. Search for **Mobilités M**.
3. Select your line (e.g., `C5`), your departure stop (e.g., `Rosa Parks`), then choose the direction and destination stop.
4. Add the **Mobilités M Card** directly from your dashboard's visual card picker.