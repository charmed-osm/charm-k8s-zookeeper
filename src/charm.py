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

from interface_zookeeper import ZookeeperClientEvents


class ZookeeperCharm(CharmBase):
    on = ZookeeperClientEvents()
    state = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        
        self.state.set_default(is_started=False)

        self.zookeeper = None

        if not self.state.is_started:
            self.state.is_started = True
        
        self.framework.observe(self.on.config_changed, self)
        self.framework.observe(self.on.start, self)
        self.framework.observe(self.on.upgrade_charm, self)

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

        host = self.framework.model.app.name
        config = self.framework.model.config

        zookeeper_relation = self.model.get_relation("zookeeper")
        zookeeper_data = zookeeper_relation.data[self.model.app]
        zookeeper_data["host"] = host
        zookeeper_data["port"] = config["client-port"]
        zookeeper_data["rest_port"] = config["client-port"]

        self.on.zookeeper_available.emit()

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
