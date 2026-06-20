# Kubernetes

Manifests for the full stack: Postgres, the AI service, the ingestion service
(with HPA), the streaming path (Kafka + the consumer worker), the frontend, an
ingress, and the monitoring stack (Prometheus, Alertmanager, Grafana, Jaeger and
a webhook sink). Applies as a single kustomization.

`monitoring-config/` holds copies of the root `monitoring/` configs, because
kustomize cannot read files outside its own directory; keep them in sync.

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

The monitoring UIs are `ClusterIP` services; reach them with port-forward:

```bash
kubectl -n log-guardian port-forward svc/grafana 3000:3000     # dashboards
kubectl -n log-guardian port-forward svc/jaeger 16686:16686    # traces
kubectl -n log-guardian port-forward svc/prometheus 9090:9090  # metrics/alerts
```

## Notes

- Secrets here use plain `stringData` for clarity — use a real secret manager
  (sealed-secrets, External Secrets, SOPS) in production.
- The HPA needs metrics-server installed in the cluster.
