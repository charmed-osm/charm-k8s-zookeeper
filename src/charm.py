#!/usr/bin/env python3

import sys

sys.path.append("lib")

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    WaitingStatus,
    ModelError,
)


class ZookeeperCharm(CharmBase):
    state = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        # An example of setting charm state
        # that's persistent across events
        self.state.set_default(is_started=False)

        if not self.state.is_started:
            self.state.is_started = True

        # Register all of the events we want to observe
        for event in (
            # Charm events
            self.on.config_changed,
            self.on.start,
            self.on.upgrade_charm,
        ):
            self.framework.observe(event, self)

    def _apply_spec(self, spec):
        # Only apply the spec if this unit is a leader.
        if self.framework.model.unit.is_leader():
            self.framework.model.pod.set_spec(spec)
            self.state.spec = spec

    def make_pod_spec(self):
        config = self.framework.model.config
        spec = {
            "version": 2,
            "containers": [
                {
                    "name": self.framework.model.app.name,
                    "image": config["image"],
                    "ports": [
                        {"name": "client", "containerPort": config["client-port"]},
                        {"name": "server", "containerPort": config["server-port"]},
                        {
                            "name": "leader-election",
                            "containerPort": config["leader-election-port"],
                        },
                    ],
                    "kubernetes": {
                        "readinessProbe": {
                            "tcpSocket": {"port": config["client-port"]},
                            "initialDelaySeconds": 10,
                            "timeoutSeconds": 5,
                            "failureThreshold": 6,
                        },
                        "livenessProbe": {
                            "tcpSocket": {"port": config["client-port"]},
                            "initialDelaySeconds": 10,
                        },
                    },
                    "command": [
                        "sh",
                        "-c",
                        "start-zookeeper --servers={} --data_dir=/var/lib/zookeeper/data  --data_log_dir=/var/lib/zookeeper/data/log  --conf_dir=/opt/zookeeper/conf".format(
                            config["num-units"]
                        ),
                    ],
                }
            ],
        }

        return spec

    def on_config_changed(self, event):
        """Handle changes in configuration"""
        unit = self.model.unit

        new_spec = self.make_pod_spec()
        if self.state.spec != new_spec:
            unit.status = MaintenanceStatus("Applying new pod spec")

            self._apply_spec(new_spec)

            unit.status = ActiveStatus()

    def on_start(self, event):
        """Called when the charm is being installed"""
        unit = self.model.unit

        unit.status = MaintenanceStatus("Applying pod spec")

        new_pod_spec = self.make_pod_spec()
        self._apply_spec(new_pod_spec)

        unit.status = ActiveStatus()

    def on_upgrade_charm(self, event):
        """Upgrade the charm."""
        unit = self.model.unit

        # Mark the unit as under Maintenance.
        unit.status = MaintenanceStatus("Upgrading charm")

        self.on_start(event)

        # When maintenance is done, return to an Active state
        unit.status = ActiveStatus()


if __name__ == "__main__":
    main(ZookeeperCharm)
