# Q-PRIME generated data controller

`qprime-devices` is an idle controller for the paper's ten-device testbed. It
does **not** generate records when Compose starts. In the Q-PRIME dashboard's
**Data Sources** tab, users choose exactly one generated mode:

- **Simulator** — select sensors and configure their interval, refresh rate,
  added latency, degraded-record percentage, low-significance percentage and
  privacy filter. Records are posted directly to `/api/ingest`.
- **Sample EdgeX Feed** — provision the whole testbed in EdgeX and submit each
  reading through device-rest and the HTTP-export pipeline.

Starting either mode stops the other. Stop generation from the same tab; do not
stop the controller container, because the dashboard uses it for configuration
and status. The last simulator configuration persists in MongoDB, but a
running workload is never resumed after Docker restarts.

It is a **demonstration input, not a replacement for a real device service**.
The decision engine, QoC scoring and placement algorithm it exercises are the
real implementation; only the selected device readings are generated.

## Devices

| Device | Stream | Refresh | Notes |
|---|---|---|---|
| `LabDoorSensor_1` | `door` | 650 ms | contact events |
| `LabDoorSensor_2` | `door` | 650 ms | contact events |
| `LabTHPSensor` | `thp` | 650 ms | temperature / humidity / pressure |
| `SoilMoisture_1` | `soil` | 800 ms | `moisture_pct`, conductivity |
| `SmokeDetector_1` | `smoke` | 500 ms | `smoke_ppm`, occasional alarm events |
| `HeartMonitor_1` | `heart` | 500 ms | carries a patient identity (PII) |
| `ZED2i` | `zed_vision` | 800 ms | person detections (PII) |
| `Misty Robot 1` | `misty_vision` | 810 ms | face recognition (PII) |
| `Tello Drone 1` | `tello_vision` | 1000 ms | `privacy_filter: strict`, pinned to edge |
| `RGBCamera_1` | `camera_vision` | 900 ms | person detections (PII) |

Payloads match `services/core/schema/*-schema.json`, so the QoC completeness
factor is scored against the same field sets the paper used — including the
structured `entity` carrying `gateway_id` and `location`. Numeric payload fields
use the canonical names declared in `repository.RECORD_FIELDS`
(`temperature`, `humidity`, `pressure`, `moisture_pct`, `smoke_ppm`, `bpm`), which
are the ones the SQL surface and the sensor dashboard can read.

A configurable fraction of records is emitted degraded (a dropped or
out-of-range field) to exercise completeness, and every stream emits periodic
`heartbeat` events to exercise significance. Correctness stays at 1.0 unless you
configure `correctness_rules` — see [documents/METRICS.md](../../documents/METRICS.md).

## Container configuration

| Variable | Default | Effect |
|---|---|---|
| `QPRIME_CORE_URL` | `http://qprime-analysis:5005` | Core ingestion endpoint |
| `QPRIME_SAMPLE_RATE_PER_MIN` | `60` | Sample EdgeX Feed records per minute |

## EdgeX route

The Sample EdgeX Feed registers one REST device profile per stream and one
EdgeX device per simulated device in core-metadata, then pushes each reading to
`device-rest`, so records travel the full device → EdgeX core-data →
`app-service-configurable` HTTP export → `POST /api/ingest/edgex` path.

The canonical Q-PRIME metadata (`contextAttribute`, `refreshRate`,
`privacy_filter`, `device_id`, `gateway_id`) travels as EdgeX **device tags**,
which core-data copies onto every event and `normalize_edgex` reads back out.
Records arriving through EdgeX are therefore scored identically to direct
ones — including the drone's `privacy_filter: strict` edge pin.

Filter results by entry point in the Decisions tab, or via the API:

```bash
curl 'http://localhost:5005/api/results/decisions?source=edgex&limit=5'
curl 'http://localhost:5005/api/results/decisions?source=direct&limit=5'
```

If EdgeX is unavailable, Sample EdgeX Feed stops and reports the reason; it
never silently falls back to direct ingestion.
