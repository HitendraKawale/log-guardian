# Kubernetes

Manifests for the core application tier: Postgres, the AI service, the ingestion
service (with HPA), the frontend, and an ingress. Kafka and the monitoring stack
are intentionally out of scope here — run those via Docker Compose or add their
own manifests.

## Build images

The deployments use locally-built images (`imagePullPolicy: IfNotPresent`).
With minikube:

```bash
eval $(minikube docker-env)
docker build -t log-guardian/ai-service:latest        services/ai-service
docker build -t log-guardian/ingestion-service:latest services/ingestion-service
docker build -t log-guardian/frontend:latest          frontend
```

## Deploy

```bash
kubectl apply -k infrastructure/kubernetes
kubectl -n log-guardian get pods
```

The ingestion image runs `alembic upgrade head` on startup, so the schema is
created automatically once Postgres is reachable.

## Access

Add to `/etc/hosts` (minikube ip):

```
<minikube-ip>  log-guardian.local api.log-guardian.local
```

Then open <http://log-guardian.local/?api=http://api.log-guardian.local>.

## Notes

- Secrets here use plain `stringData` for clarity — use a real secret manager
  (sealed-secrets, External Secrets, SOPS) in production.
- The HPA needs metrics-server installed in the cluster.
