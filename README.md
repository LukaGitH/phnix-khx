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
- Numeric unit ID / slave address (`1`–`247`, usually `1`)
- Polling interval in seconds (default `10`)

The integration checks the connection with a read-only register request before saving the device. The polling interval can be changed later from the integration's options.

## Keep test data out of History

Home Assistant's Recorder controls saved history, so this setting is in Home Assistant's `recorder:` configuration rather than the heat pump setup form. To keep the live entities available without saving their state changes, add these exclusions to `configuration.yaml` and restart Home Assistant:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.phnix_khx_*
      - number.phnix_khx_*
      - switch.phnix_khx_*
      - select.phnix_khx_*
```

These patterns match the default device name, **Phnix KHX**. If you chose another name or renamed entities, check their actual entity IDs in **Settings → Devices & services → Entities** and adjust the patterns. If you already have a `recorder:` section, add the patterns to its existing `exclude.entity_globs` list rather than creating a second section. Recorder exclusions stop future history; previously saved history remains until it is purged. Remove the patterns and restart Home Assistant when you want to start recording.

## Manual install

Copy `custom_components/phnix_khx` from this repository into the `custom_components` directory in your Home Assistant configuration, then restart Home Assistant.
