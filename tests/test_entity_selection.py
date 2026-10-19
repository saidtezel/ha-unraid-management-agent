"""Test choosing which groups of entities the integration creates."""

from __future__ import annotations

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.unraid_management_agent.const import CONF_ENTITY_GROUPS
from custom_components.unraid_management_agent.entity_selection import (
    ENTITY_GROUPS,
    GROUP_ARRAY_CONTROLS,
    GROUP_CONTAINER_CONTROLS,
    GROUP_CONTAINER_SENSORS,
    GROUP_DISK_SENSORS,
    GROUP_DISK_SPIN_CONTROLS,
    GROUP_NETWORK_SENSORS,
    GROUP_PLUGIN_UPDATES,
    GROUP_POWER_CONTROLS,
    GROUP_REMOTE_SHARES,
    GROUP_SERVICES,
    GROUP_SHARE_SENSORS,
    GROUP_USER_SCRIPTS,
    GROUP_VM_CONTROLS,
    GROUP_VM_SENSORS,
    entity_group,
    selected_groups,
)


@pytest.mark.parametrize(
    ("platform", "key", "group"),
    [
        (Platform.SWITCH, "container_plex_abc123", GROUP_CONTAINER_CONTROLS),
        (Platform.SWITCH, "container_plex_autostart", GROUP_CONTAINER_CONTROLS),
        (Platform.BUTTON, "container_plex_restart", GROUP_CONTAINER_CONTROLS),
        (Platform.SENSOR, "container_plex_cpu", GROUP_CONTAINER_SENSORS),
        (Platform.BINARY_SENSOR, "container_updates_available", None),
        (Platform.UPDATE, "container_plex_update", None),
        (Platform.SWITCH, "vm_windows_10", GROUP_VM_CONTROLS),
        (Platform.BUTTON, "vm_win_1a2b3c_force_stop", GROUP_VM_CONTROLS),
        (Platform.SENSOR, "vm_windows_10_cpu", GROUP_VM_SENSORS),
        (Platform.SENSOR, "vmguest_windows_10_hostname", GROUP_VM_SENSORS),
        (Platform.BUTTON, "array_start", GROUP_ARRAY_CONTROLS),
        (Platform.BUTTON, "parity_check_pause", GROUP_ARRAY_CONTROLS),
        (Platform.BUTTON, "system_reboot", GROUP_POWER_CONTROLS),
        (Platform.SWITCH, "disk_sdb_spin", GROUP_DISK_SPIN_CONTROLS),
        (Platform.SENSOR, "disk_sdb_temperature", GROUP_DISK_SENSORS),
        (Platform.SENSOR, "share_media_usage", GROUP_SHARE_SENSORS),
        (Platform.BINARY_SENSOR, "network_eth0", GROUP_NETWORK_SENSORS),
        (Platform.BINARY_SENSOR, "network_service_ssh", GROUP_SERVICES),
        (Platform.BINARY_SENSOR, "system_service_nginx", GROUP_SERVICES),
        (Platform.BUTTON, "user_script_backup", GROUP_USER_SCRIPTS),
        (Platform.SWITCH, "remote_share_nas_mount", GROUP_REMOTE_SHARES),
        (Platform.SENSOR, "remote_share_nas_usage", GROUP_REMOTE_SHARES),
        (Platform.UPDATE, "plugin_unassigned_devices", GROUP_PLUGIN_UPDATES),
        (Platform.UPDATE, "os_update", None),
        (Platform.SENSOR, "cpu_usage", None),
        (Platform.BINARY_SENSOR, "array_started", None),
        (Platform.NUMBER, "fan_speed_fan1", None),
    ],
)
def test_entity_group(platform: Platform, key: str, group: str | None) -> None:
    """Entities are grouped by key and platform; core entities have no group."""
    assert entity_group(platform, key) == group


def test_selected_groups_default_to_all() -> None:
    """Entries from before the option existed keep every group."""
    assert selected_groups({}) == frozenset(ENTITY_GROUPS)
    assert selected_groups({CONF_ENTITY_GROUPS: []}) == frozenset()


def _unique_ids(hass: HomeAssistant, entry_id: str) -> set[str]:
    """Return the unique IDs of the entry's registry entries."""
    registry = er.async_get(hass)
    return {
        entity.unique_id
        for entity in er.async_entries_for_config_entry(registry, entry_id)
    }


@pytest.mark.usefixtures(
    "mock_unraid_client_class",
    "mock_unraid_websocket_client_class",
)
async def test_unselected_groups_are_not_created_and_removed(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Unticking groups removes their entities; core entities stay."""
    entry_id = mock_config_entry.entry_id
    await hass.config_entries.async_setup(entry_id)
    await hass.async_block_till_done()

    before = _unique_ids(hass, entry_id)
    container_switch_ids = {
        entity.unique_id
        for entity in er.async_entries_for_config_entry(er.async_get(hass), entry_id)
        if entity.domain == Platform.SWITCH
        and entity.unique_id.startswith(f"{entry_id}_container_")
    }
    assert container_switch_ids
    assert f"{entry_id}_array_start" in before
    assert f"{entry_id}_cpu_usage" in before

    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={**mock_config_entry.options, CONF_ENTITY_GROUPS: []},
    )
    await hass.config_entries.async_reload(entry_id)
    await hass.async_block_till_done()

    after = _unique_ids(hass, entry_id)
    assert not container_switch_ids & after
    assert f"{entry_id}_array_start" not in after
    assert f"{entry_id}_cpu_usage" in after
    assert all(
        entity_group(entity.domain, entity.unique_id.removeprefix(f"{entry_id}_"))
        is None
        for entity in er.async_entries_for_config_entry(er.async_get(hass), entry_id)
    )

    # Ticking a group again brings its entities back
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            **mock_config_entry.options,
            CONF_ENTITY_GROUPS: [GROUP_CONTAINER_CONTROLS],
        },
    )
    await hass.config_entries.async_reload(entry_id)
    await hass.async_block_till_done()

    assert container_switch_ids <= _unique_ids(hass, entry_id)
    assert f"{entry_id}_array_start" not in _unique_ids(hass, entry_id)
