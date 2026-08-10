# Architecture

Q-PRIME is the paper implementation that processes raw context records. It
accepts external producers and real EdgeX devices, and includes two optional,
user-started demonstration producers. The same pipeline processes direct and
EdgeX records, so both receive the same QoC evaluation, privacy checks,
weighting, placement decision, and persistent evidence.

```mermaid
flowchart TB
    subgraph Input[Inputs and user-started sources]
        Direct[External producer<br/>POST /api/ingest]
        Simulator[Simulator<br/>user-started, direct]
        Sample[Sample EdgeX Feed<br/>user-started]
        Device[Real device or gateway]
        EdgeX[EdgeX Foundry]
        Sample --> EdgeX
        Device --> EdgeX
    end

    subgraph Pipeline[Q-PRIME paper pipeline]
        CoreApi[Core API]
        Ingest[Normalise and deduplicate]
        Policy[Resolve device, stream, or global policy]
        Evaluate[QoC baseline and five-factor evaluation]
        Privacy[PII detection and privacy controls]
        Score[Criteria weights or AHP<br/>score Edge / Cloud / Both]

        CoreApi --> Ingest --> Policy --> Evaluate --> Privacy --> Score
    end

    Direct -->|POST /api/ingest| CoreApi
    Simulator -->|POST /api/ingest| CoreApi
    EdgeX -->|HTTP export<br/>/api/ingest/edgex| CoreApi

    subgraph Persistence[Placement and persistent evidence]
        Edge[(MongoDB<br/>edge_records)]
        LocalCloud[(MongoDB<br/>cloud_records fallback)]
        AWS[AWS Kinesis or Firehose<br/>when configured]
        Evidence[(MongoDB<br/>placements, profiles, baselines, audit)]
    end

    Score -->|Edge or Both| Edge
    Score -->|Cloud or Both; AWS unavailable or write fails| LocalCloud
    Score -->|Cloud or Both; AWS configured| AWS
    Score --> Evidence
    CoreApi -->|configuration and dashboard reads| Evidence
    Policy <--> Evidence
    Evaluate <--> Evidence

    subgraph ReadPaths[Query and visualisation]
        Web[Query application<br/>and Q-PRIME dashboard<br/>localhost:3000]
        NLP[NLP service<br/>natural language to SQL]
        Router[Core query router<br/>read-only SQL]
        Presto[PrestoDB<br/>MongoDB Edge and local Cloud]
        Athena[Athena<br/>active AWS Cloud]
    end

    Web -->|natural-language query| NLP --> Router
    Web -->|SQL query| Router
    Web -->|results and configuration APIs| CoreApi
    Web -->|new tab| Console[EdgeX Console<br/>localhost:4000]
    Router --> Presto
    Router -->|AWS Cloud is configured| Athena
    AWS --> Athena
```

## Record processing and policy

A direct producer posts a canonical record to `/api/ingest`. A real-device
integration sends an EdgeX event, which the bundled HTTP-export service
forwards to `/api/ingest/edgex`. Q-PRIME normalises either payload, creates or
uses a stable record identifier, and ignores repeated deliveries.

## Generated sources and EdgeX management

The Q-PRIME dashboard is also the control plane for optional generated inputs.
Its **Data Sources** tab begins in **Off** mode. A user can start either the
direct Simulator (with per-sensor timing, QoC degradation and privacy settings)
or the Sample EdgeX Feed (the paper testbed flowing through EdgeX), never both.
The selected configuration is stored in MongoDB, but running state is never
restored after a restart. This prevents a deployed stack from creating data
without an explicit user action.

The dashboard's **Open EdgeX Console** link opens EdgeX's official management
UI in a separate tab. It is used to inspect and configure registered EdgeX
device services, profiles, devices, readings and commands. To connect physical
hardware, the user must also deploy the compatible EdgeX device-service driver;
the Console is a manager, not a universal hardware driver.

Before scoring a record, Q-PRIME resolves the active policy in this order:
device override → stream override → global profile. The policy provides the
criteria weights directly or derives them from the AHP matrix. The pipeline
then evaluates timeliness, completeness, correctness, resolution, and
significance; detects PII; applies strict privacy controls; and calculates the
paper’s Edge and Cloud scores. A tie recommends Both.

## Placement and persistence

An Edge recommendation is retained in MongoDB `edge_records`. A Cloud
recommendation writes to AWS Kinesis or Firehose only when AWS is configured;
otherwise, or when that write fails, Q-PRIME retains the raw record in MongoDB
`cloud_records` as a local Cloud fallback. A Both recommendation applies both
active storage rules.

Every placement also writes an immutable decision record containing the QoC
scores, effective policy version, recommendation, actual backend, privacy
findings, reason, and timings. MongoDB also persists policy versions, audit
history, adaptive QoC baselines, and query metrics. Existing local Cloud
fallback records are never copied to AWS when AWS later becomes available.

## AWS configuration and credential protection

AWS Cloud settings are configured in the Q-PRIME dashboard rather than in an
application `.env` file. The dashboard sends its region, delivery stream, and
optional Athena settings to the core API, which persists the active
configuration in MongoDB and immediately applies it to future placements and
Cloud queries. Static access keys, secret access keys, and optional session
tokens are encrypted before being written to MongoDB; the API returns only
whether credentials are configured, never their values.

The Compose stack keeps the encryption key in the `qprime-core-secrets` Docker
volume, separate from the MongoDB data volume. Both volumes must be retained
for a saved AWS configuration to remain usable after restart. Removing the
secrets volume makes the previously encrypted credentials unreadable, so they
must then be entered again through the dashboard.

## Query and dashboard paths

The query application and the `/qprime` dashboard share the Next.js web
application on port 3000 but have separate responsibilities. The query
application accepts SQL or natural-language questions; the NLP service turns
natural language into SQL, and the core query router validates that SQL before
selecting its physical source.

PrestoDB reads the MongoDB Edge and local Cloud fallback collections. When
AWS Cloud is configured, Cloud queries are sent to Athena instead; earlier
local fallback records remain in MongoDB and are not included in the active
Cloud query path. The `/qprime` dashboard reads the persistent decision,
configuration, QoC, privacy, and performance projections directly from the
core API, so it continues to show the placement history across Cloud cutover.
