"""The awair component."""

from asyncio import gather
from typing import Any, Optional

from async_timeout import timeout
from python_awair import AwairLocal

from homeassistant.const import CONF_HOSTS
from homeassistant.core import Config, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import API_LOCAL_TIMEOUT, DOMAIN, LOGGER, UPDATE_INTERVAL, AwairResult

PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, config: Config) -> bool:
    """Set up Awair integration."""
    return True


async def async_setup_entry(hass, config_entry) -> bool:
    """Set up Awair integration from a config entry."""
    session = async_get_clientsession(hass)
    coordinator = AwairDataUpdateCoordinator(hass, config_entry, session)

    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = coordinator

    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(config_entry, platform)
        )

    return True


async def async_unload_entry(hass, config_entry) -> bool:
    """Unload Awair configuration."""
    tasks = []
    for platform in PLATFORMS:
        tasks.append(
            hass.config_entries.async_forward_entry_unload(config_entry, platform)
        )

    unload_ok = all(await gather(*tasks))
    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok


class AwairDataUpdateCoordinator(DataUpdateCoordinator):
    """Define a wrapper class to update Awair data."""

    _awair: AwairLocal

    def __init__(self, hass, config_entry, session) -> None:
        """Set up the AwairDataUpdateCoordinator class."""
        device_addrs_str = config_entry.data[CONF_HOSTS]
        device_addrs = [addr.strip() for addr in device_addrs_str.split(",")]
        self._awair = AwairLocal(session=session, device_addrs=device_addrs)
        self._config_entry = config_entry

        super().__init__(hass, LOGGER, name=DOMAIN, update_interval=UPDATE_INTERVAL)

    async def _async_update_data(self) -> Optional[Any]:
        """Update data via Awair client library."""
        with timeout(API_LOCAL_TIMEOUT):
            try:
                LOGGER.debug("Fetching devices")
                devices = await self._awair.devices()
                results = await gather(
                    *[self._fetch_air_data(device) for device in devices]
                )
                return {result.device.uuid: result for result in results}
            except Exception as err:
                raise UpdateFailed(err)

    async def _fetch_air_data(self, device):
        """Fetch latest air quality data."""
        LOGGER.debug("Fetching data for %s", device.uuid)
        air_data = await device.air_data_latest()
        LOGGER.debug(air_data)
        return AwairResult(device=device, air_data=air_data)
