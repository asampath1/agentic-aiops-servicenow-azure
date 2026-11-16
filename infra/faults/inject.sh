#!/usr/bin/env bash
# Inject (or clear) a real fault on the demo VM through Run Command, so a real Azure Monitor alert fires.
#   infra/faults/inject.sh cpu     # runaway python3 on every vCPU (self-stops after 45 min) -> vm-cpu-high
#   infra/faults/inject.sh disk    # an orders-debug.log that leaves ~5% free on /           -> vm-disk-low
#   infra/faults/inject.sh status  # load, top processes, disk usage
#   infra/faults/inject.sh clear   # stop the runaway and remove the big log (manual reset, not the runbook)
# The faults mirror the dataset's root causes ("runaway python3 process", "log rotation disabled") and log a
# warning to syslog the way the app would, which is where the Diagnostics agent finds the process name.
set -euo pipefail
ACTION="${1:-status}"
RG="${RG:-rg-skr-aiops-demo}"
VM="${VM:-vm-orders-app-01}"

case "$ACTION" in
  cpu) SCRIPT='
for i in $(seq "$(nproc)"); do
  setsid nohup timeout 45m python3 -c "while True: pass" >/dev/null 2>&1 &
done
sleep 2
logger -p user.warning -t orders-report "python3 report worker stuck in a loop, consuming 100% CPU (pids $(pgrep -d, -f "while True: pass"))"
echo "runaway python3 started on $(nproc) vCPU(s); self-stops after 45 min"; uptime' ;;
  disk) SCRIPT='
mkdir -p /var/log/skr-orders
avail=$(df --output=avail -B1 / | tail -1); size=$(df --output=size -B1 / | tail -1)
fill=$(( avail - size / 20 ))
fallocate -l "$fill" /var/log/skr-orders/orders-debug.log
logger -p user.warning -t orders-app "log rotation disabled: /var/log/skr-orders/orders-debug.log is $((fill / 1073741824)) GB, disk / almost full"
df -h / | tail -1' ;;
  status) SCRIPT='
uptime; echo; ps -eo pid,pcpu,comm --sort=-pcpu | head -5; echo; df -h / | tail -1; ls -lh /var/log/skr-orders 2>/dev/null || true' ;;
  clear) SCRIPT='
pkill -f "while True: pass" && echo "runaway python3 stopped" || echo "no runaway python3"
rm -f /var/log/skr-orders/orders-debug.log /var/log/skr-orders/orders-debug.log.tail && echo "removed orders-debug.log"
df -h / | tail -1' ;;
  *) echo "usage: $0 cpu|disk|status|clear" >&2; exit 2 ;;
esac

az vm run-command invoke -g "$RG" -n "$VM" --command-id RunShellScript --scripts "$SCRIPT" \
  --query "value[0].message" -o tsv
