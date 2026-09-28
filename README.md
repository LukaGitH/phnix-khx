# Phnix KHX Heat Pump for Home Assistant

A local Modbus TCP integration for Phnix KHX heat pumps. It provides sensor, number, switch, and select entities.

## Install with HACS

1. In HACS, open **Integrations** and choose **Custom repositories** from the menu.
2. Add `https://github.com/LukaGitH/phnix-khx` with category **Integration**.
3. Install **Phnix KHX Heat Pump**, then restart Home Assistant.

## Add the heat pump

After restarting, open **Settings → Devices & services → Add integration**, search for **Phnix KHX Heat Pump**, and enter:

- A name for this heat pump
- The IP address or hostname of its Modbus TCP gateway
- Modbus TCP port (usually `502`)
- Unit ID / slave address (usually `1`)
- Polling interval in seconds (default `10`)

The integration checks the connection with a read-only register request before saving the device. The polling interval can be changed later from the integration's options.

## Manual install

Copy `custom_components/phnix_khx` from this repository into the `custom_components` directory in your Home Assistant configuration, then restart Home Assistant.
