# Phnix KHX Heat Pump for Home Assistant

A local Modbus TCP integration for Phnix KHX heat pumps. It provides sensor, number, switch, and select entities and can run alongside a Home Assistant `modbus:` configuration.

## Install with HACS

1. In HACS, open **Integrations** and choose **Custom repositories** from the menu.
2. Add `https://github.com/LukaGitH/phnix-khx` with category **Integration**.
3. Install **Phnix KHX Heat Pump**, then restart Home Assistant.

## Manual install

Copy `custom_components/phnix_khx` from this repository into the `custom_components` directory in your Home Assistant configuration, then restart Home Assistant.

## Configure

Add one or more devices to `configuration.yaml`:

```yaml
phnix_khx:
  - name: Phnix KHX
    host: 192.168.0.194
    port: 502
    slave: 1
    scan_interval: 10
```

Set `host` to the IP address of the heat pump's Modbus TCP gateway. `port` defaults to `502`, `slave` defaults to `1`, and `scan_interval` is in seconds. After editing YAML, restart Home Assistant.

The integration reads the configured registers and exposes supported writable settings as entities. Confirm your wiring, gateway settings, and unit ID before enabling control entities.
