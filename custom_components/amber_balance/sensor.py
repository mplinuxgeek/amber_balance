from __future__ import annotations

import asyncio
import calendar
from datetime import date, datetime, timedelta, timezone
import logging

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.update_coordinator import UpdateFailed, DataUpdateCoordinator

from .const import (
    BASE_URL,
    DEFAULT_NAME,
    DEFAULT_SUBSCRIPTION,
    DEFAULT_SURCHARGE_CENTS,
    CONF_NAME,
    CONF_SITE_ID,
    CONF_SITE_IDS,
    CONF_SUBSCRIPTION,
    CONF_SURCHARGE_CENTS,
    CONF_TOKEN,
    DOMAIN,
    ISO_DATE,
)

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_TOKEN): cv.string,
        vol.Optional(CONF_SITE_ID): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_SURCHARGE_CENTS, default=DEFAULT_SURCHARGE_CENTS): vol.Coerce(
            float
        ),
        vol.Optional(CONF_SUBSCRIPTION, default=DEFAULT_SUBSCRIPTION): vol.Coerce(
            float
        ),
    }
)


async def async_setup_platform(hass: HomeAssistant, config, add_entities, discovery_info=None):
    token = config[CONF_TOKEN]
    name = config[CONF_NAME]
    surcharge_cents = config[CONF_SURCHARGE_CENTS]
    subscription = config[CONF_SUBSCRIPTION]

    session = async_get_clientsession(hass)
    site_ids = []
    if config.get(CONF_SITE_ID):
        site_ids = [config[CONF_SITE_ID]]
    else:
        site_ids = await AmberApi.discover_sites(session, token)
    sensors = []
    for sid in site_ids:
        api = AmberApi(session, token, sid)
        sensors.append(
            AmberBalanceSensor(
                api=api,
                name=f"{name} ({sid[:6]})",
                surcharge_cents=surcharge_cents,
                subscription=subscription,
            )
        )
    add_entities(sensors, update_before_add=True)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    data = entry.data
    session = async_get_clientsession(hass)
    site_ids = data.get(CONF_SITE_IDS) or []
    if not site_ids and data.get(CONF_SITE_ID):
        site_ids = [data[CONF_SITE_ID]]
    sensors = []
    for sid in site_ids:
        api = AmberApi(session, data[CONF_TOKEN], sid)
        sensors.append(
            AmberBalanceSensor(
                api=api,
                name=f"{data.get(CONF_NAME, DEFAULT_NAME)} ({sid})",
                surcharge_cents=data.get(CONF_SURCHARGE_CENTS, DEFAULT_SURCHARGE_CENTS),
                subscription=data.get(CONF_SUBSCRIPTION, DEFAULT_SUBSCRIPTION),
            )
        )
    async_add_entities(sensors, update_before_add=True)


class AmberApi:
    def __init__(self, session: aiohttp.ClientSession, token: str, site_id: str):
        self._session = session
        self._token = token
        self._site_id = site_id

    @staticmethod
    async def discover_sites(session: aiohttp.ClientSession, token: str) -> list[str]:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "amber-balance/0.3",
        }
        url = BASE_URL + "/sites"
        async with async_timeout.timeout(30):
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"GET {url} -> {resp.status}: {text[:200]}")
                data = await resp.json()
        site_ids = []
        if isinstance(data, list):
            for s in data:
                sid = s.get("id") or s.get("siteId") or s.get("site_id")
                if sid:
                    site_ids.append(str(sid))
        return site_ids

    async def fetch_usage(self, start: date, end: date) -> list[dict]:
        records: list[dict] = []
        cur = start
        while cur <= end:
            chunk_end = min(cur + timedelta(days=6), end)
            params = f"startDate={cur.strftime(ISO_DATE)}&endDate={chunk_end.strftime(ISO_DATE)}"
            data = await self._get(f"/sites/{self._site_id}/usage?{params}")
            if isinstance(data, list):
                records.extend(data)
            cur = chunk_end + timedelta(days=1)
        return records

    async def _get(self, path: str):
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "User-Agent": "amber-balance/0.2",
        }
        url = BASE_URL + path
        try:
            async with async_timeout.timeout(30):
                async with self._session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"GET {url} -> {resp.status}: {text[:200]}")
                    return await resp.json()
        except asyncio.TimeoutError as e:
            raise RuntimeError(f"GET {url} timed out") from e


class AmberBalanceSensor(SensorEntity):
    _attr_should_poll = False

    def __init__(
        self,
        api: AmberApi,
        name: str,
        surcharge_cents: float,
        subscription: float,
    ):
        self._api = api
        self._attr_name = name
        self._surcharge_cents = surcharge_cents
        self._subscription = subscription
        self._attr_icon = "mdi:currency-usd"
        self._attr_native_unit_of_measurement = "AUD"
        self._state = None
        self._attr_extra_state_attributes = {ATTR_ATTRIBUTION: "Data from amber.com.au"}
        self._coordinator: DataUpdateCoordinator | None = None

    @property
    def unique_id(self):
        site_suffix = self._api._site_id or "default"
        return f"{DOMAIN}_{site_suffix}_position"

    @property
    def native_value(self):
        return self._state

    async def async_added_to_hass(self):
        await self._ensure_coordinator()
        await self._coordinator.async_config_entry_first_refresh()
        self.async_on_remove(self._coordinator.async_add_listener(self._handle_coordinator_update))

    async def _ensure_coordinator(self):
        if self._coordinator:
            return
        self._coordinator = DataUpdateCoordinator(
            self.hass,
            _LOGGER,
            name=self._attr_name or "Amber Balance",
            update_method=self._async_update_data,
            update_interval=timedelta(hours=1),
        )

    async def _async_update_data(self):
        try:
            nem_tz = timezone(timedelta(hours=10))
            today = datetime.now(nem_tz).date()
            # Current month from day 1 up to yesterday
            start = date(today.year, today.month, 1)
            end = today - timedelta(days=1)

            records = await self._api.fetch_usage(start, end)
            daily = self._summaries(records, start, end)
            totals = self._totals(daily)

            self._state = round(totals["position"], 2)
            self._attr_extra_state_attributes = {
                ATTR_ATTRIBUTION: "Data from amber.com.au",
                "range_start": start.isoformat(),
                "range_end": end.isoformat(),
                "import_kwh": round(totals["import_kwh"], 2),
                "export_kwh": round(totals["export_kwh"], 2),
                "import_cost": round(totals["import_cost"], 2),
                "export_earnings": round(totals["export_earnings"], 2),
                "total": round(totals["total_cost"], 2),
                "surcharge": round(totals["surcharge"], 2),
                "subscription": round(totals["subscription"], 2),
                "position": round(totals["position"], 2),
                "daily": daily,
            }
            return True
        except Exception as err:
            raise UpdateFailed(f"Amber Balance update failed: {err}") from err

    async def async_update(self):
        await self._ensure_coordinator()
        if self._coordinator:
            await self._coordinator.async_request_refresh()

    def _summaries(self, records: list[dict], start: date, end: date):
        by_date: dict[str, list[dict]] = {}
        for rec in records:
            d = rec.get("date")
            if not d:
                continue
            by_date.setdefault(d, []).append(rec)

        daily = []
        cur = start
        while cur <= end:
            key = cur.strftime(ISO_DATE)
            daily.append(self._summarize_day(key, by_date.get(key, [])))
            cur += timedelta(days=1)
        return daily

    def _summarize_day(self, dkey: str, records: list[dict]):
        import_cost = 0.0
        export_earnings = 0.0
        import_kwh = 0.0
        export_kwh = 0.0
        for rec in records:
            cost = rec.get("cost") or 0.0
            kwh = rec.get("kwh") or 0.0
            channel_type = rec.get("channelType")
            if channel_type == "feedIn":
                export_earnings += cost
                export_kwh += abs(kwh)
            else:
                import_cost += cost
                import_kwh += kwh
        import_cost /= 100.0
        export_earnings /= 100.0
        total_cost = import_cost + export_earnings

        surcharge = self._surcharge_cents / 100.0
        days_in_month = calendar.monthrange(int(dkey[:4]), int(dkey[5:7]))[1]
        subscription = self._subscription / days_in_month
        position = total_cost + surcharge + subscription
        return {
            "date": dkey,
            "import_kwh": import_kwh,
            "export_kwh": export_kwh,
            "import_cost": import_cost,
            "export_earnings": export_earnings,
            "total_cost": total_cost,
            "surcharge": surcharge,
            "subscription": subscription,
            "position": position,
        }

    def _totals(self, daily: list[dict]):
        agg = {
            "import_kwh": 0.0,
            "export_kwh": 0.0,
            "import_cost": 0.0,
            "export_earnings": 0.0,
            "total_cost": 0.0,
            "surcharge": 0.0,
            "subscription": 0.0,
            "position": 0.0,
        }
        for d in daily:
            for k in agg:
                agg[k] += d[k]
        return agg

    def _handle_coordinator_update(self):
        # Coordinator already updated state/attrs in _async_update_data
        self.async_write_ha_state()
