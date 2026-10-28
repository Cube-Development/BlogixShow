# System Overview

The main services of the marketplace and how they talk to each other.

Back to the project overview: [README](../README.md).

---

## Component diagram

```mermaid
flowchart LR
    %% ---------- clients ----------
    subgraph Clients
        WEB["Website<br/><i>Next.js</i>"]
        ADM["Admin panel<br/><i>React</i>"]
        CRMF["CRM frontend<br/><i>React</i>"]
        TGU["Telegram users"]
    end

    ING{{"Ingress<br/>TLS termination"}}

    %% ---------- core ----------
    subgraph CORE["Core (one codebase, three processes)"]
        API["Core API<br/><i>FastAPI</i><br/>REST /api/v1, webhooks"]
        BOT["Telegram bot<br/><i>aiogram 3</i>"]
        WRK["Core worker<br/><i>FastStream</i><br/>event consumers"]
    end

    %% ---------- satellite services ----------
    subgraph SAT["Satellite services"]
        CRM["CRM API<br/><i>FastAPI</i><br/>agencies, deals"]
        REP["Report service<br/>PDF / Excel reports"]
        SCH["Scheduler<br/><i>taskiq</i><br/>periodic jobs, reminders"]
        MGR["Userbot manager<br/>channel statistics,<br/>post checks"]
        UB["Telegram userbots<br/>one pod per account"]
        TAX["Tax service adapter<br/>legal entity checks,<br/>fiscal receipts"]
    end

    %% ---------- data / infrastructure ----------
    subgraph DATA["Data and messaging"]
        PG[("PostgreSQL cluster<br/>primary + replicas,<br/>PgBouncer rw / ro")]
        CRMDB[("CRM database")]
        NATS[["NATS JetStream<br/>streams, KV, object store"]]
        RDS[("Redis<br/>cache, bot state, locks")]
        MAN[("Manticore<br/>full-text search")]
        CEN["Centrifugo<br/>real-time"]
        S3[("S3 storage<br/>media, reports,<br/>screenshots, documents")]
    end

    %% ---------- external ----------
    subgraph EXT["External services"]
        TGAPI["Telegram API"]
        PAY["Payment gateways"]
        EDO["E-document service"]
        GOV["National tax service"]
        AUTH["Google OAuth"]
        AI["OpenAI"]
        MAIL["Email provider"]
        SOC["Social network APIs<br/>Instagram, YouTube"]
    end

    %% clients -> edge
    WEB --> ING
    ADM --> ING
    CRMF --> ING
    ING --> API
    ING --> CRM
    ING -- websocket --> CEN
    TGU <--> TGAPI
    TGAPI -- updates --> BOT

    %% core internals
    BOT --> PG
    BOT --> RDS
    API --> PG
    API --> RDS
    API --> MAN
    API --> S3
    API -- publish --> CEN
    API -- events --> NATS
    WRK -- consume / publish --> NATS
    WRK --> PG
    WRK --> MAN

    %% satellites
    NATS <-->|"report requests / responses"| REP
    REP --> S3
    SCH -- jobs --> NATS
    SCH --> RDS
    API -- HTTP --> MGR
    MGR -- NATS --> UB
    UB -- MTProto --> TGAPI
    API -- HTTP --> TAX
    TAX --> GOV
    CRM --> CRMDB
    CRM --> S3

    %% external from core
    API --> PAY
    PAY -- webhooks --> API
    API --> EDO
    EDO -- webhooks --> API
    API --> AUTH
    API --> AI
    WRK --> MAIL
    WRK --> SOC
```

## Services

| Service | Role | Talks to |
|---------|------|----------|
| **Core API** | The main backend: auth, catalog, carts, projects, orders, wallet, chats, admin API. Receives webhooks from payment and e-document services. | PostgreSQL, Redis, Manticore, S3, Centrifugo, NATS, satellites over HTTP |
| **Telegram bot** | Order notifications for bloggers, accepting orders, project creation from Telegram, submission and verification of published posts. Calls the same use cases as the API. | Telegram API, PostgreSQL, Redis |
| **Core worker** | Consumes domain events from NATS: order and project changes, notifications, search index updates, channel sync, chats. | NATS, PostgreSQL, Manticore, email, social networks |
| **Report service** | Builds PDF / Excel reports on request over NATS and returns the result. Heavy rendering is kept out of the API process. | NATS, S3 |
| **Scheduler** | Periodic jobs: publication reminders, deadlines, recurring sync. A taskiq scheduler plus a pool of workers. | NATS, Redis |
| **Userbot manager** | Manages Telegram user accounts that read channel statistics and check posts where the Bot API is not enough. Each account runs in its own pod. | Core API (HTTP), NATS, Telegram (MTProto) |
| **Tax service adapter** | Isolated integration with the national tax system: legal entity validation, fiscal data. Runs separately because it needs its own certificates. | Core API (HTTP), tax service |
| **CRM** | A separate product for advertising agencies: clients, deals, documents. Has its own database. Planned to use the marketplace as the executor of placements. | its own PostgreSQL, S3 |
| **Website / Admin panel / CRM frontend** | Single-page clients. | APIs through the ingress |

## Communication styles

| Style | Used for | Why |
|-------|----------|-----|
| **HTTP (sync)** | client → API, API → userbot manager, API → tax adapter, external webhooks | the caller needs the answer right now |
| **NATS events (async)** | API → worker, worker → worker | side effects that must not slow down or fail the user request |
| **NATS request / reply** | API ↔ report service | long-running jobs with a result |
| **Transactional outbox** | API → NATS | an event is published only if the database transaction committed |
| **Centrifugo** | API → browser | real-time chats and notifications without polling |

## Deployment

```mermaid
flowchart TB
    subgraph K8S["Kubernetes cluster"]
        direction TB
        subgraph EDGE["Edge"]
            ING["Ingress controller<br/>+ cert-manager (Let's Encrypt)"]
        end
        subgraph APPS["Applications"]
            A1["core-api ×2"]
            A2["core-worker"]
            A3["telegram-bot"]
            A4["report-web + report-broker"]
            A5["scheduler + scheduler-workers"]
            A6["userbot-manager + broker"]
            A7["userbot per account ×N"]
            A8["tax-adapter"]
            A9["crm-api"]
            A10["website / admin / crm-front<br/>(nginx)"]
        end
        subgraph STATE["Stateful"]
            P["PostgreSQL<br/>(CloudNativePG operator,<br/>scheduled backups to S3)"]
            N["NATS JetStream"]
            R["Redis"]
            M["Manticore"]
            C["Centrifugo"]
        end
        subgraph JOBS["One-off jobs"]
            J1["DB migrations<br/>(core, CRM, manager)"]
            J2["NATS streams / KV init"]
            J3["Search index rebuild"]
        end
        subgraph OBS["Observability"]
            PR["Prometheus"]
            GR["Grafana"]
            AM["Alertmanager → Telegram"]
        end
    end
    CI["GitHub Actions<br/>build image → registry → rollout"] --> APPS
    S3[("S3 storage")]
    P -. backups .-> S3
    APPS -. metrics .-> PR
    PR --> GR
    PR --> AM
    APPS -. errors .-> SEN["Sentry"]
```

- Every service is a Docker image deployed by GitHub Actions.
- Database migrations and NATS / search initialization run as Kubernetes Jobs before a rollout.
- PostgreSQL runs under an operator with replicas, a read-write and a read-only connection pooler, and scheduled backups to object storage.
- Alerts from Prometheus go to a Telegram chat.
