#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

: "${IMAGES_APP:?Set IMAGES_APP, for example: export IMAGES_APP=your-images-app}"

FLY_ORG="${FLY_ORG:-harbour-ml-solution-course}"
CLASSIFIER_IMAGE_TAG="${CLASSIFIER_IMAGE_TAG:-classifier-v1}"
CLASSIFIER_IMAGE="registry.fly.io/$IMAGES_APP:$CLASSIFIER_IMAGE_TAG"

if ! command -v fly >/dev/null 2>&1; then
  echo "fly CLI is not installed. Install it from https://fly.io/docs/flyctl/install/" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI is not installed or Docker Desktop is not running." >&2
  exit 1
fi

fly auth whoami >/dev/null

if ! fly apps list --org "$FLY_ORG" --quiet | awk '{print $1}' | grep -qx "$IMAGES_APP"; then
  fly apps create "$IMAGES_APP" --org "$FLY_ORG" --yes
fi

fly auth docker

docker build --platform linux/amd64 -t "$CLASSIFIER_IMAGE" ./services/classifier
docker push "$CLASSIFIER_IMAGE"
docker manifest inspect "$CLASSIFIER_IMAGE" >/dev/null

echo "Classifier sidecar image pushed:"
echo "  $CLASSIFIER_IMAGE"
echo
echo "Use this for deployment:"
echo "  export CLASSIFIER_IMAGE=$CLASSIFIER_IMAGE"
