# YouAreBot Fly.io Microservices

This repository contains a small production-style ML microservice system for the
Session 13 Fly.io deployment homework.

## Services

`docker-compose.yaml` starts three local services:

1. `orchestrator` - public FastAPI API exposing `POST /predict`.
2. `classifier` - internal FastAPI classifier service exposing `POST /score`.
3. `postgres` - database for prediction requests and results.

The public API accepts user text, calls the classifier service, stores the
prediction result in Postgres, and returns the prediction.

## Local Run

```bash
docker compose up --build
```

Public API:

```text
http://127.0.0.1:6872
```

Test readiness and prediction:

```bash
./scripts/03_test.sh http://127.0.0.1:6872
```

Manual test:

```bash
curl -X POST http://127.0.0.1:6872/predict \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello"}'
```

Recent stored predictions:

```bash
curl http://127.0.0.1:6872/predictions/recent
```

## Fly.io Deployment

The deployment follows the `fly_compose_microservices/` pattern from the lecture
repository. Fly runs one public app with three containers in the same Machine:

```text
client -> https://<compose-app>.fly.dev/predict
       -> orchestrator container :8000
       -> classifier sidecar on localhost:8001
       -> postgres sidecar on localhost:5432
```

Set the app names assigned by the instructor:

```bash
export FLY_ORG=harbour-ml-solution-course
export FLY_REGION=fra
export COMPOSE_APP=<your-compose-app>
export IMAGES_APP=<your-images-app>
```

Build and push the classifier sidecar image:

```bash
./scripts/01_build_push_images.sh
```

Deploy the public Fly app:

```bash
./scripts/02_deploy_fly.sh
```

Test the deployed endpoint:

```bash
./scripts/03_test.sh https://$COMPOSE_APP.fly.dev
```

The public URL to register on youare.bot is:

```text
https://<your-compose-app>.fly.dev
```

## Generated Files

The deploy script generates these local files:

```text
fly.generated.toml
docker-compose.fly.yml
```

They contain personal Fly app names and are intentionally ignored by Git.

## Secrets

No API keys, tokens, or passwords for external accounts are committed. The local
demo Postgres password is only for the disposable containerized homework setup.
