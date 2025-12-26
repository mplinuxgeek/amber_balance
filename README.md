## Amber Balance (Home Assistant)

A Home Assistant custom integration that calculates your current Amber electricty position by summing monthly usage, feed-in, surcharges, and subscription costs. It exposes a single sensor with helpful attributes summarising the current billing month.

### Installation (HACS)
- Add this repository to HACS: `HACS → Integrations → Custom repositories → https://github.com/bircoe/amber_balance` with category `Integration`.
- Install **Amber Balance** from HACS, then restart Home Assistant so the integration is loaded.
- In Home Assistant, go to **Settings → Devices & services → Add integration → Amber Balance** and follow the prompts.

### Manual installation
- Copy the `custom_components/amber_balance` folder into your Home Assistant `config/custom_components` directory.
- Restart Home Assistant.
- Add the **Amber Balance** integration from **Settings → Devices & services**.

### Configuration
- **Amber API token** (required): generated via the Amber API portal.
- **Site ID** (optional): if omitted, sites are discovered automatically and the first site is used.
- **Name** (optional): defaults to `Amber Balance`.
- **Surcharge (cents/day)** and **Subscription ($/month)** are used when calculating the running position.
