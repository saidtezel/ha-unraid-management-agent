"""
Entity group selection for the Unraid Management Agent integration.

Users pick which groups of entities (container switches, VM buttons, disk
sensors, ...) the integration creates. Entities outside every group (system,
array and UPS sensors, the update and event entities, ...) are always created.

Groups are matched on the entity key (the unique ID after ``{entry_id}_``)
and the platform, so every platform shares one filter: each wraps its
``async_add_entities`` callback with ``async_filter_add_entities``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, Final

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import CONF_ENTITY_GROUPS

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity import Entity
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

_LOGGER = logging.getLogger(__name__)

GROUP_CONTAINER_CONTROLS: Final = "container_controls"
GROUP_CONTAINER_SENSORS: Final = "container_sensors"
GROUP_VM_CONTROLS: Final = "vm_controls"
GROUP_VM_SENSORS: Final = "vm_sensors"
GROUP_ARRAY_CONTROLS: Final = "array_controls"
GROUP_POWER_CONTROLS: Final = "power_controls"
GROUP_DISK_SPIN_CONTROLS: Final = "disk_spin_controls"
GROUP_DISK_SENSORS: Final = "disk_sensors"
GROUP_SHARE_SENSORS: Final = "share_sensors"
GROUP_NETWORK_SENSORS: Final = "network_sensors"
GROUP_SERVICES: Final = "services"
GROUP_USER_SCRIPTS: Final = "user_scripts"
GROUP_REMOTE_SHARES: Final = "remote_shares"
GROUP_UNASSIGNED_DEVICES: Final = "unassigned_devices"
GROUP_PLUGIN_UPDATES: Final = "plugin_updates"

# Groups in the order the selector shows them
ENTITY_GROUPS: Final[tuple[str, ...]] = (
    GROUP_CONTAINER_CONTROLS,
    GROUP_CONTAINER_SENSORS,
    GROUP_VM_CONTROLS,
    GROUP_VM_SENSORS,
    GROUP_ARRAY_CONTROLS,
    GROUP_POWER_CONTROLS,
    GROUP_DISK_SPIN_CONTROLS,
    GROUP_DISK_SENSORS,
    GROUP_SHARE_SENSORS,
    GROUP_NETWORK_SENSORS,
    GROUP_SERVICES,
    GROUP_USER_SCRIPTS,
    GROUP_REMOTE_SHARES,
    GROUP_UNASSIGNED_DEVICES,
    GROUP_PLUGIN_UPDATES,
)

# Preselected when a server is added: monitoring only, no controls. Entries
# created before the option existed have no stored value and keep every group,
# so upgrading never removes entities.
DEFAULT_NEW_ENTRY_GROUPS: Final[tuple[str, ...]] = (
    GROUP_DISK_SENSORS,
    GROUP_SHARE_SENSORS,
)

_CONTROL_PLATFORMS: Final = frozenset({Platform.SWITCH, Platform.BUTTON})

# Static keys that share a dynamic prefix but belong to no group
_UNGROUPED_KEYS: Final = frozenset({"container_updates_available"})

_ARRAY_CONTROL_KEYS: Final = frozenset(
    {
        "array_start",
        "array_stop",
        "array_clear_disk_stats",
        "parity_check_start",
        "parity_check_stop",
        "parity_check_pause",
        "parity_check_resume",
    }
)
_POWER_CONTROL_KEYS: Final = frozenset({"system_shutdown", "system_reboot"})

# Prefix rules checked in order: (key prefix, group for control platforms,
# group for every other platform). None leaves the entity ungrouped.
_PREFIX_RULES: Final[tuple[tuple[str, str | None, str | None], ...]] = (
    ("container_", GROUP_CONTAINER_CONTROLS, GROUP_CONTAINER_SENSORS),
    ("vmguest_", None, GROUP_VM_SENSORS),
    ("vm_", GROUP_VM_CONTROLS, GROUP_VM_SENSORS),
    ("disk_", GROUP_DISK_SPIN_CONTROLS, GROUP_DISK_SENSORS),
    ("share_", None, GROUP_SHARE_SENSORS),
    ("network_service_", None, GROUP_SERVICES),
    ("system_service_", None, GROUP_SERVICES),
    ("network_", None, GROUP_NETWORK_SENSORS),
    ("user_script_", GROUP_USER_SCRIPTS, None),
    ("remote_share_", GROUP_REMOTE_SHARES, GROUP_REMOTE_SHARES),
    ("unassigned_device_", None, GROUP_UNASSIGNED_DEVICES),
)


def entity_group(platform: str, key: str) -> str | None:
    """Return the selectable group of an entity, or None if it is always created."""
    if key in _UNGROUPED_KEYS:
        return None
    if key in _ARRAY_CONTROL_KEYS:
        return GROUP_ARRAY_CONTROLS
    if key in _POWER_CONTROL_KEYS:
        return GROUP_POWER_CONTROLS
    if platform == Platform.UPDATE:
        return GROUP_PLUGIN_UPDATES if key.startswith("plugin_") else None
    is_control = platform in _CONTROL_PLATFORMS
    for prefix, control_group, other_group in _PREFIX_RULES:
        if key.startswith(prefix):
            return control_group if is_control else other_group
    return None


def selected_groups(options: Mapping[str, Any]) -> frozenset[str]:
    """Return the selected groups; every group when the option was never set."""
    stored = options.get(CONF_ENTITY_GROUPS)
    if stored is None:
        return frozenset(ENTITY_GROUPS)
    return frozenset(stored)


def _is_selected(
    entry: ConfigEntry, platform: str, unique_id: str | None, groups: frozenset[str]
) -> bool:
    """Return True when the entity's group is selected (or it has none)."""
    prefix = f"{entry.entry_id}_"
    if not unique_id or not unique_id.startswith(prefix):
        return True
    group = entity_group(platform, unique_id[len(prefix) :])
    return group is None or group in groups


def async_filter_add_entities(
    entry: ConfigEntry,
    platform: Platform,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> AddConfigEntryEntitiesCallback:
    """Wrap a platform's add callback so it drops entities of unselected groups."""
    groups = selected_groups(entry.options)

    def _add(new_entities: Iterable[Entity], *args: Any, **kwargs: Any) -> None:
        kept = [
            entity
            for entity in new_entities
            if _is_selected(entry, platform, entity.unique_id, groups)
        ]
        if kept:
            async_add_entities(kept, *args, **kwargs)

    return _add


@callback
def async_remove_unselected_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove registry entries of entities whose group is no longer selected."""
    groups = selected_groups(entry.options)
    registry = er.async_get(hass)
    removed = 0
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if not _is_selected(entry, entity.domain, entity.unique_id, groups):
            registry.async_remove(entity.entity_id)
            removed += 1
    if removed:
        _LOGGER.debug("Removed %d entities of unselected entity groups", removed)
