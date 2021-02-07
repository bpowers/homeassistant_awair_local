"""Config flow for Awair."""

from typing import Optional

from python_awair import Awair, AwairLocal
from python_awair.exceptions import AuthError, AwairError
import voluptuous as vol

from homeassistant.config_entries import CONN_CLASS_CLOUD_POLL, ConfigFlow, CONN_CLASS_LOCAL_POLL
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, LOGGER  # pylint: disable=unused-import


class AwairFlowHandler(ConfigFlow, domain=DOMAIN):
    """Config flow for Awair."""

    VERSION = 2
    CONNECTION_CLASS = CONN_CLASS_CLOUD_POLL

    async def async_step_zeroconf(self, zeroconf_info):
        """Set up locally discovered devices."""
        ip_addr = zeroconf_info.get("host", None)
        hostname = zeroconf_info.get("hostname", None)
        if ip_addr is None or hostname is None:
            # TODO: fixme
            return self.async_abort(reason="unknown")

        device = await self._get_local_info(ip_addr)
        if device is None:
            # TODO: fixme
            return self.async_abort(reason="unknown")

        await self.async_set_unique_id(device.uuid)
        self._abort_if_unique_id_configured()

        self.local_device = device
        self.local_name = hostname.split(".")[0]
        self.context["title_placeholders"] = {
            "name": self.local_name
        }
        LOGGER.debug(self.local_device)
        LOGGER.debug(self.local_name)
        LOGGER.debug(self.context)
        return await self.async_step_confirm_discovery()


    async def async_step_confirm_discovery(self, user_input=None):
        """Confirm addition of discovered device."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"Local device: {self.local_name}",
                data={
                    "host": self.local_device.device_addr,
                    "local": True,
                }
            )

        return self.async_show_form(
            step_id="confirm_discovery",
            errors={},
            description_placeholders={
                "name": self.local_name,
            },
        )



    async def async_step_import(self, conf: dict):
        """Import a configuration from config.yaml."""
        if self.hass.config_entries.async_entries(DOMAIN):
            return self.async_abort(reason="already_setup")

        user, error = await self._check_connection(conf[CONF_ACCESS_TOKEN])
        if error is not None:
            return self.async_abort(reason=error)

        await self.async_set_unique_id(user.email)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"{user.email} ({user.user_id})",
            data={
                CONF_ACCESS_TOKEN: conf[CONF_ACCESS_TOKEN],
                "local": False
            },
        )

    async def async_step_user(self, user_input: Optional[dict] = None):
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is not None:
            user, error = await self._check_connection(user_input[CONF_ACCESS_TOKEN])

            if user is not None:
                await self.async_set_unique_id(user.email)
                self._abort_if_unique_id_configured()

                title = f"{user.email} ({user.user_id})"
                return self.async_create_entry(title=title, data={**user_input, "local": False})

            if error != "invalid_access_token":
                return self.async_abort(reason=error)

            errors = {CONF_ACCESS_TOKEN: "invalid_access_token"}

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ACCESS_TOKEN): str}),
            errors=errors,
        )

    async def async_step_reauth(self, user_input: Optional[dict] = None):
        """Handle re-auth if token invalid."""
        errors = {}

        if user_input is not None:
            access_token = user_input[CONF_ACCESS_TOKEN]
            _, error = await self._check_connection(access_token)

            if error is None:
                for entry in self._async_current_entries():
                    if entry.unique_id == self.unique_id:
                        self.hass.config_entries.async_update_entry(
                            entry, data={**user_input, "local": False}
                        )

                        return self.async_abort(reason="reauth_successful")

            if error != "invalid_access_token":
                return self.async_abort(reason=error)

            errors = {CONF_ACCESS_TOKEN: error}

        return self.async_show_form(
            step_id="reauth",
            data_schema=vol.Schema({vol.Required(CONF_ACCESS_TOKEN): str}),
            errors=errors,
        )

    async def _check_connection(self, access_token: str):
        """Check the access token is valid."""
        session = async_get_clientsession(self.hass)
        awair = Awair(access_token=access_token, session=session)

        try:
            user = await awair.user()
            devices = await user.devices()
            if not devices:
                return (None, "no_devices_found")

            return (user, None)

        except AuthError:
            return (None, "invalid_access_token")
        except AwairError as err:
            LOGGER.error("Unexpected API error: %s", err)
            return (None, "unknown")

    async def _get_local_info(self, ip_addr: str):
        """Get local Awair device info."""
        session = async_get_clientsession(self.hass)
        awair = AwairLocal(session=session, device_addrs=[ip_addr])

        try:
            devices = await awair.devices()
            return devices[0]
        except AwairError as err:
            LOGGER.error("Unexpected API error: %s", err)
            return None
