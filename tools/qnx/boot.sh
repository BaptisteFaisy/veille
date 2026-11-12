#!/usr/bin/env bash
# Veille — recette de démarrage de la VM QNX 8.0 (recette de preuve).
#
#   bash tools/qnx/boot.sh            # démarre la VM et attend SSH
#   bash tools/qnx/boot.sh --stop     # arrête la VM (PID file)
#   bash tools/qnx/boot.sh --status   # état de la VM
#
# Paramètres (variables d'environnement) :
#   QNX_VM_DIR   répertoire de la VM   (défaut ~/qnx800/images/qemu/qemu)
#   SSH_PORT     port SSH-forwardé     (défaut 8022)
#   SERIAL_PORT  port console série   (défaut 4444)
#   MEM          RAM de la VM en Mio   (défaut 3072)
#   CPUS         vCPUs                 (défaut 4)
#
# L'image est l'image « Quick Start Target Image » (QNX Everywhere) du SDP 8.0 ;
# l'accès SSH est root par clé (pas de mot de passe), la console série sert au
# débogage (login root/root). Le démarrage est déterministe : mêmes options
# QEMU à chaque fois, un seul PID file, arrêt propre.
set -euo pipefail

QNX_VM_DIR=${QNX_VM_DIR:-$HOME/qnx800/images/qemu/qemu}
SSH_PORT=${SSH_PORT:-8022}
SERIAL_PORT=${SERIAL_PORT:-4444}
MEM=${MEM:-3072}
CPUS=${CPUS:-4}
CLE=${CLE:-$HOME/.ssh/qnx-vm_ed25519}
PIDFILE="$QNX_VM_DIR/output/qemu.pid"
ACTION=${1:-start}

qemu_pid() {
  [ -f "$PIDFILE" ] || return 1
  local p; p=$(cat "$PIDFILE" 2>/dev/null || true)
  [ -n "$p" ] || return 1
  kill -0 "$p" 2>/dev/null || return 1
  echo "$p"
}

ssh_ok() {
  ssh -p "$SSH_PORT" -i "$CLE" -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null -o ConnectTimeout=5 -o BatchMode=yes \
      root@127.0.0.1 'uname -s' >/dev/null 2>&1
}

case "$ACTION" in
  --stop|--stop*)
    if p=$(qemu_pid); then
      echo "[boot] arrêt de la VM QNX (pid $p)"
      kill "$p" 2>/dev/null || true
      for _ in $(seq 1 20); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
      kill -9 "$p" 2>/dev/null || true
      rm -f "$PIDFILE"
      echo "[boot] arrêtée"
    else
      echo "[boot] aucune VM à arrêter (pidfile $PIDFILE)"
    fi
    ;;
  --status)
    if p=$(qemu_pid); then echo "[boot] VM vivante (pid $p)"; else echo "[boot] VM arrêtée"; fi
    if ssh_ok; then echo "[boot] SSH joignable sur $SSH_PORT"; else echo "[boot] SSH injoignable"; fi
    ;;
  --start|--start*)
    if p=$(qemu_pid); then
      echo "[boot] VM déjà vivante (pid $p)"
    else
      [ -f "$QNX_VM_DIR/output/ifs.bin" ] || { echo "[boot] image absente : $QNX_VM_DIR/output/ifs.bin" >&2; exit 1; }
      echo "[boot] démarrage QEMU ($QNX_VM_DIR)"
      cd "$QNX_VM_DIR"
      nohup qemu-system-x86_64 -smp "$CPUS" --enable-kvm --cpu host -m "${MEM}M" \
        -drive file=output/disk-qemu.vmdk,if=ide,id=drv0 -kernel output/ifs.bin \
        -pidfile output/qemu.pid -display none -vga none \
        -chardev socket,id=ser0,host=127.0.0.1,port="$SERIAL_PORT",server=on,wait=off \
        -serial chardev:ser0 \
        -netdev user,id=net0,hostfwd=tcp:127.0.0.1:"$SSH_PORT"-:22 \
        -device virtio-net-pci,netdev=net0 \
        -object rng-random,filename=/dev/urandom,id=rng0 -device virtio-rng-pci,rng=rng0 \
        >/dev/null 2>&1 &
      sleep 3
      p=$(qemu_pid) || { echo "[boot] QEMU n'a pas démarré" >&2; exit 1; }
      echo "[boot] QEMU pid $p — attente du guest (SSH $SSH_PORT)"
    fi
    for i in $(seq 1 40); do
      if ssh_ok; then echo "[boot] VM prête (${i} essai(s))"; exit 0; fi
      sleep 3
    done
    echo "[boot] délai dépassé : le guest ne répond pas sur $SSH_PORT" >&2
    exit 1
    ;;
  *)
    echo "usage: $0 [--start|--stop|--status]" >&2
    exit 2
    ;;
esac
