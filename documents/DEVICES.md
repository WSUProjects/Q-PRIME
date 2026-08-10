# Connecting data producers

Q-PRIME accepts raw context records from an external producer or from an EdgeX
deployment. Both inputs use the same QoC, privacy, weighting, placement, and
persistence pipeline. This repository does not generate device data.

## Direct ingestion

Send one JSON context record to `POST http://localhost:5005/api/ingest`.
The required fields are `contextAttribute`, `contextValue`, and `resource`.
Use a scalar `entity` value when supplied; it is normally the device name.

```json
{
  "contextAttribute": "misty_vision",
  "contextValue": {
    "event": "familiar_face_detected",
    "person": "Alice",
    "distance": 56
  },
  "entity": "Misty Robot 1",
  "resource": {
    "device_id": "misty_03953",
    "device_name": "Misty Robot 1",
    "sensor_id": "misty_vision",
    "gateway_id": "edge-node-4"
  },
  "refreshRate": 1000,
  "timestamp": 1785000000,
  "privacy_filter": false
}
```

`timestamp` may be Unix seconds or milliseconds. Q-PRIME creates a stable
record ID when one is not supplied, so repeated delivery of the same record is
idempotent. Set `privacy_filter` to `true` or `"strict"` to force that record
to the Edge tier.

The current paper stream keys are:

- `camera_vision`
- `door`
- `heart`
- `misty_vision`
- `smoke`
- `soil`
- `tello_vision`
- `thp`
- `zed_vision`

The aliases `misty`, `tello`, and `zed` map to their corresponding vision
streams. Other stream names are accepted and use the active global policy
until a stream-specific profile is created.

## EdgeX ingestion

The default Compose deployment includes EdgeX and the `app-http-export-qprime`
application service. Configure a compatible EdgeX device service or producer
to publish EdgeX event envelopes. The bundled export service forwards them to
`POST http://qprime-analysis:5005/api/ingest/edgex` inside the Compose network.
The same endpoint is exposed to the host as
`http://localhost:5005/api/ingest/edgex`.

For each EdgeX reading, Q-PRIME preserves the event origin, device name,
resource name, and reading identifier, then converts it to the canonical
context-record shape. EdgeX deliveries receive the same placement decision as
direct records and are marked with source `edgex`.

The locally exposed EdgeX endpoints include core data on port `59880`, core
metadata on port `59881`, and device-rest on port `59986`. Device provisioning
and transport setup remain the responsibility of the connected device service
or external integration.

## Configuring a stream

Use the **Q-PRIME Dashboard → Configuration** page at
`http://localhost:3000/qprime` to configure the current paper streams with:

- per-stream direct criteria weights;
- global direct criteria weights; or
- a three-criterion AHP pairwise matrix.

Profiles are persisted in MongoDB and resolved in the order device → stream →
global. Saving a profile affects later records only; it does not move existing
records between Edge and Cloud storage.

For API-driven administration, inspect the active profiles with
`GET /api/config`, update the global profile with `PUT /api/config`, or create
a versioned global, stream, or device profile with `POST /api/config/profiles`.
