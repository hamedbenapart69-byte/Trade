#!/bin/sh
set -eu
mkdir -p /var/lib/control
# Persistent volumes may be mounted root-owned. Fix only the mount root, then
# drop privileges before starting the application.
chown 10001:10001 /var/lib/control
exec gosu 10001:10001 "$@"
