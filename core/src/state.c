#include "veille/state.h"
#include <stdio.h>
#include <string.h>

static const char *SENSOR_NAMES[VEILLE_SENSOR__COUNT] = {
    "sensor_ok", "sensor_stuck", "sensor_dead", "sensor_noisy", "sensor_drift"
};
static const char *BUS_NAMES[VEILLE_BUS__COUNT] = {
    "bus_ok", "bus_saturated", "bus_spike"
};
static const char *PRIO_MODE_NAMES[VEILLE_PRIO_MODE__COUNT] = {
    "prio_normal", "prio_inverted"
};
static const char *ALARM_NAMES[VEILLE_ALARM__COUNT] = {
    "alarm_none", "alarm_single", "alarm_concurrent", "alarm_locked", "alarm_acked"
};

const char *veille_sensor_state_name(veille_sensor_state s) {
    return (s >= 0 && s < VEILLE_SENSOR__COUNT) ? SENSOR_NAMES[s] : "?";
}
const char *veille_bus_state_name(veille_bus_state b) {
    return (b >= 0 && b < VEILLE_BUS__COUNT) ? BUS_NAMES[b] : "?";
}
const char *veille_prio_mode_name(veille_prio_mode p) {
    return (p >= 0 && p < VEILLE_PRIO_MODE__COUNT) ? PRIO_MODE_NAMES[p] : "?";
}
const char *veille_alarm_state_name(veille_alarm_state a) {
    return (a >= 0 && a < VEILLE_ALARM__COUNT) ? ALARM_NAMES[a] : "?";
}

int veille_state_chain_broken(const veille_fault_state *st) {
    if (!st) return 1;
    unsigned critical = (1u << VEILLE_STAGE_ACQUIRE) | (1u << VEILLE_STAGE_FILTER)
                      | (1u << VEILLE_STAGE_DECIDE)  | (1u << VEILLE_STAGE_ALARM);
    return (st->stage_fault_mask & critical) ? 1 : 0;
}

long veille_state_worst_latency_ms(const veille_chain_config *cfg, const veille_fault_state *st) {
    if (!cfg || !st) return -1;
    if (veille_state_chain_broken(st)) return -1;  /* chaîne rompue → alarme technique */
    long sum = 0;
    for (int i = 0; i < VEILLE_STAGE__COUNT; i++) sum += cfg->stage_latency_ms[i];
    if (st->sensor == VEILLE_SENSOR_STUCK) sum += 5;
    if (st->sensor == VEILLE_SENSOR_NOISY) sum += 10;
    if (st->sensor == VEILLE_SENSOR_DRIFT) sum += 8;
    if (st->bus == VEILLE_BUS_SATURATED)   sum += 30;
    if (st->bus == VEILLE_BUS_SPIKE)       sum += 50;
    if (st->prio == VEILLE_PRIO_INVERTED)  sum += 40;
    if (st->alarm == VEILLE_ALARM_CONCURRENT) sum += 15;
    return sum;
}

void veille_state_to_string(const veille_fault_state *st, char *buf, size_t cap) {
    if (!st || !buf || cap == 0) return;
    buf[0] = '\0';
    size_t off = 0;
    const char *parts[4] = {
        veille_sensor_state_name(st->sensor),
        veille_bus_state_name(st->bus),
        veille_prio_mode_name(st->prio),
        veille_alarm_state_name(st->alarm)
    };
    for (int i = 0; i < 4; i++) {
        if (i > 0 && off + 1 < cap) { buf[off++] = '|'; buf[off] = '\0'; }
        size_t len = strlen(parts[i]);
        if (off + len < cap) { memcpy(buf + off, parts[i], len); off += len; buf[off] = '\0'; }
    }
    if (st->stage_fault_mask && off + 24 < cap) {
        int w = snprintf(buf + off, cap - off, "|stage_fault=0x%x", st->stage_fault_mask);
        if (w > 0) off += (size_t)w;
    }
}
