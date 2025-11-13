0. Ensure base image is up to date (built from insilica/toxindex repo)
# The base image (us-docker.pkg.dev/toxindex/toxindex-backend/base:latest) 
# contains all shared code (webserver, workflows, config, dependencies).
# It should be built and pushed from the insilica/toxindex repository.
# This repo only builds tool-specific images that extend the base.

1. Connect to GKE
gcloud container clusters get-credentials toxindex-gke \
  --region us-east4 \
  --project toxindex

2. Clear hard-drive space 
docker system prune -af
docker volume prune -f

3. Build Docker image

# Note: Base image is built from insilica/toxindex repo and pushed to registry.
docker build -f dockerfile/Dockerfile.base -t us-docker.pkg.dev/toxindex/toxindex-backend/base:latest .
docker push us-docker.pkg.dev/toxindex/toxindex-backend/base:latest
# This repo only builds tool-specific images that extend the shared base.

# Build tool-specific image (no need to build base image here)
docker build -f dockerfile/Dockerfile.[toolname] -t us-docker.pkg.dev/toxindex/toxindex-backend/[toolname]:latest .

# Example for buildKE:
docker build -f dockerfile/Dockerfile.buildKE -t us-docker.pkg.dev/toxindex/toxindex-backend/buildke:latest .
docker push us-docker.pkg.dev/toxindex/toxindex-backend/buildke:latest
kubectl rollout restart deployment celery-worker-buildke -n toxindex-app

5. apply deployment, check status
kubectl apply -f deployment.yaml --validate=false

kubectl get pods -n toxindex-app -l app=celery-worker-[yourtool]
kubectl describe deployment/celery-worker-[yourtool] -n toxindex-app
kubectl logs deployment/celery-worker-[yourtool] -n toxindex-app

kubectl describe deployment/celery-worker-buildke -n toxindex-app
kubectl logs deployment/celery-worker-buildke -n toxindex-app

6. Setup VPA for automatic resource scaling (prevents OOM kills)
# First, check if VPA is installed:
kubectl get crd verticalpodautoscalers.autoscaling.k8s.io

# If not installed, install VPA (requires cluster admin):
# For GKE, VPA can be enabled via: gcloud container clusters update CLUSTER_NAME --enable-vertical-pod-autoscaling

# Apply VPA configuration:
kubectl apply -f vpa-buildke.yaml


# Check VPA status:
kubectl get vpa celery-worker-buildke-vpa -n toxindex-app
kubectl describe vpa celery-worker-buildke-vpa -n toxindex-app

7. redeploy if necessary
kubectl rollout restart deployment celery-worker-buildke -n toxindex-app

8. update frontend

A. add a field to resources>default_workflows.json

{
  "workflow_id": 6,
  "frontend_id": "toxindex-sygma",
  "title": "toxindex-sygma",
  "label": "Sygma Analysis",
  "description": "Sygma analysis is blah blah.",
  "initial_prompt": "Enter pathway ID (e.g., WP3657) or upload data file",
  "celery_task": "metabolite-sygma"
}

B. source resources/load_postgres_env.sh && uv run python resources/seed_workflows.py

C. source resources/load_postgres_env.sh && uv run python resources/inspect_workflows.py
