# Q-PRIME dashboard metrics guide

Open the paper dashboard at <http://localhost:3000/qprime>. It reads persisted
MongoDB placement evidence and refreshes every 10 seconds. The dashboard is
separate from the query application at <http://localhost:3000/>.

## Overview

The overview shows the current persisted placement totals:

- **Records processed** — all placement decisions retained by Q-PRIME.
- **Stored at Edge** — records recommended for Edge.
- **Cloud decisions** — records recommended for Cloud; this is a placement
  recommendation count, not a guarantee of a successful external AWS write.
- **Both tiers** — records recommended for Both.
- **Cloud retained locally** — Cloud-recommended records held in MongoDB when
  AWS is unavailable or a configured write fails.
- **PII records** — records whose payload contains detected PII.

The two charts show stacked placement recommendations per device and the
overall Edge/Cloud/Both split.

## QoC Factors

Q-PRIME persists the five per-record QoC scores:

- timeliness;
- completeness;
- correctness;
- resolution; and
- significance.

The dashboard plots the most recent persisted scores over time and their mean
per device. These are raw persisted decision values, not fixed time buckets.

### Correctness is unconfigured by default

`config/qoc_thresholds.json` ships no `correctness_rules`, because valid ranges
are a per-deployment policy decision rather than a property of the framework.
With no rules configured the factor's only check is that `resource.device_id` is
present, so it scores 1.0 on essentially every record and plots as a flat line.
That is the shipped default, not a data-quality signal.

To make it discriminate, add per-stream rules — each is checked against a path
in the canonical record:

```json
"correctness_rules": {
  "thp": [
    { "path": "contextValue.temperature", "type": "number", "min": -40, "max": 85 },
    { "path": "contextValue.humidity",    "type": "number", "min": 0,   "max": 100 },
    { "path": "contextValue.battery",     "type": "number", "min": 0,   "max": 100 }
  ],
  "door": [
    { "path": "contextValue.state", "type": "string", "allowed": ["open", "closed"] },
    { "path": "contextValue.contact", "type": "boolean", "required": true }
  ]
}
```

Supported keys are `path`, `type` (`string`, `number`, `integer`, `boolean`,
`object`, `array`), `min`, `max`, `allowed` and `required`. Rules can also be set
per profile scope through the Configuration API, so they are versioned and
audited like every other policy change.

## Decisions

The decision table lists recent records with their device, stream,
recommendation, `S_edge`, `S_cloud`, resolved profile version, actual backend,
reason, and intake source. It distinguishes the paper’s recommendation from
where the record was actually retained.

## Privacy

The privacy view shows the number of PII records, PII records delivered to a
configured AWS Kinesis or Firehose backend, the resulting leak rate, and a
per-device breakdown. A locally retained Cloud fallback record is not counted
as a leak to configured AWS.

## Configuration

The Configuration tab controls the live criteria used for later placement
decisions. It supports per-paper-stream direct weights, global direct weights,
and a three-criterion AHP pairwise matrix over temporal QoC, content QoC, and
privacy. AHP saves are blocked when the consistency ratio exceeds 10%.

Profiles can be scoped globally, to one supported stream, or to one device.
Every save creates a new immutable MongoDB-backed profile version. Existing
records and decisions are not recalculated or moved.

## Query sources

The query application offers **Edge**, **Cloud**, and **Continuum** scopes.
Edge reads MongoDB through PrestoDB. Cloud reads Athena when AWS Cloud is
active, otherwise the local MongoDB Cloud-fallback collection. Continuum reads
both current sources.

## Sensitivity

Sensitivity replay evaluates the stored decision log under temporary temporal,
content, and privacy weights. It can enforce a privacy floor and optionally
force Edge for all PII. The replay displays the number of records replayed,
changed placements, replayed PII Cloud placements, and the original versus
replayed placement totals. It does not ingest, move, or alter records.

## Performance

Performance reports the number of placement and query operations measured,
their mean latency, and time-series charts for placement and query latency.
The dashboard does not provide a data-reset action, a decision CSV export, or
throughput/p50/p95 metrics.
