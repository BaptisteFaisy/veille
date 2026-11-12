#include "veille/alarm.h"

void veille_alarm_sound_profile(veille_priority p, veille_sound_profile *out) {
    if (!out) return;
    switch (p) {
        case VEILLE_PRIO_HIGH:
            out->pulses = 3; out->pulse_ms = 200; out->pause_ms = 600; break;
        case VEILLE_PRIO_MEDIUM:
            out->pulses = 2; out->pulse_ms = 300; out->pause_ms = 1200; break;
        case VEILLE_PRIO_LOW:
            out->pulses = 1; out->pulse_ms = 400; out->pause_ms = 2400; break;
        case VEILLE_PRIO_TECHNICAL:
            out->pulses = 1; out->pulse_ms = 1000; out->pause_ms = 0; break;
        default:
            out->pulses = 0; out->pulse_ms = 0; out->pause_ms = 0;
    }
}

int veille_alarm_should_fire(const veille_decision *d, const veille_fault_state *st) {
    if (!d) return 0;
    if (st && veille_state_chain_broken(st)) return 0;  /* chaîne rompue → alarme technique */
    return d->exceeded ? 1 : 0;
}

long veille_alarm_latency_ms(const veille_chain_config *cfg, const veille_fault_state *st) {
    return veille_state_worst_latency_ms(cfg, st);
}
