#!/usr/bin/env python3
# Copyright 2025 Ubuntu
# See LICENSE file for licensing details.

"""Charm the application."""

import logging

import ops
from charms.operator_libs_linux.v0.apt import PackageError, PackageNotFoundError

from langpacks import Langpacks

logger = logging.getLogger(__name__)


class LangpackVmCharm(ops.CharmBase):
    """Charm the application."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.build_langpacks_action, self._on_build_langpacks)
        self.framework.observe(self.on.upload_langpacks_action, self._on_upload_langpacks)
        self.framework.observe(self.on.stop, self._on_stop)

        self._langpacks = Langpacks()

    def _on_start(self, event: ops.StartEvent):
        """Handle start event."""
        self.unit.status = ops.MaintenanceStatus("Setting up crontab")
        self._langpacks.setup_crontab()
        self.unit.status = ops.ActiveStatus()

    def _on_install(self, event: ops.InstallEvent):
        """Handle install event."""
        self.unit.status = ops.MaintenanceStatus("Installing langpack dependencies")
        try:
            self._langpacks.install()
        except (CalledProcessError, PackageError, PackageNotFoundError):
            self.unit.status = ops.BlockedStatus(
                "Failed to install packages. Check `juju debug-log` for details."
            )
            return
        self.unit.status = ops.ActiveStatus("Ready")    

    def _on_config_changed(self, event: ops.ConfigChangedEvent):
        """Update configuration and fetch code updates"""

        self.unit.status = ops.MaintenanceStatus("Updating langpack-o-matic checkout")

        try:
            self._langpacks.update_checkout()
        except CalledProcessError:
            self.unit.status = ops.BlockedStatus(
                "Invalid configuration. Check `juju debug-log` for details."
            )
            return

    def _on_build_langpacks(self, event: ops.ActionEvent):
        """Build new langpacks"""

        self.unit.status = ops.MaintenanceStatus("Building new langpacks")
        release = event.params['release']
        base = event.params['base']

        self._langpacks.build_langpacks(base, release)

    def _on_upload_langpacks(self, event: ops.ActionEvent):
        """Upload pending langpacks"""

        self.unit.status = ops.MaintenanceStatus("Uploading the langpacks")

        self._langpacks.upload_langpacks()

    def _on_stop(self, event: ops.StopEvent):
        """Handle stop event."""
        self.unit.status = ops.MaintenanceStatus("Removing the crontab")
        self._langpacks.disable_crontab()

if __name__ == "__main__":  # pragma: nocover
    ops.main(LangpackVmCharm)
