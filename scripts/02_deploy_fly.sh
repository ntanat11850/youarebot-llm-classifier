#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

: "${COMPOSE_APP:?Set COMPOSE_APP, for example: export COMPOSE_APP=your-compose-app}"
: "${IMAGES_APP:?Set IMAGES_APP, for example: export IMAGES_APP=your-images-app}"

FLY_ORG="${FLY_ORG:-harbour-ml-solution-course}"
FLY_REGION="${FLY_REGION:-fra}"
CLASSIFIER_IMAGE_TAG="${CLASSIFIER_IMAGE_TAG:-classifier-v1}"
CLASSIFIER_IMAGE="${CLASSIFIER_IMAGE:-registry.fly.io/$IMAGES_APP:$CLASSIFIER_IMAGE_TAG}"
FLY_CONFIG="fly.generated.toml"
FLY_COMPOSE_FILE="docker-compose.fly.yml"

if ! command -v fly >/dev/null 2>&1; then
  echo "fly CLI is not installed. Install it from https://fly.io/docs/flyctl/install/" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI is not installed or Docker Desktop is not running." >&2
  exit 1
fi

fly auth whoami >/dev/null
fly auth docker

if ! docker manifest inspect "$CLASSIFIER_IMAGE" >/dev/null; then
  echo "Classifier image was not found or Docker is not authenticated:" >&2
  echo "  $CLASSIFIER_IMAGE" >&2
  echo "Run ./scripts/01_build_push_images.sh first." >&2
  exit 1
fi

sed \
  -e "s|__COMPOSE_APP__|$COMPOSE_APP|g" \
  -e "s|__FLY_REGION__|$FLY_REGION|g" \
  fly.toml.template > "$FLY_CONFIG"

sed \
  -e "s|__CLASSIFIER_IMAGE__|$CLASSIFIER_IMAGE|g" \
  docker-compose.fly.yml.template > "$FLY_COMPOSE_FILE"

fly config validate --config "$FLY_CONFIG"

if [[ "${DRY_RUN:-0}" == "1" || "${VALIDATE_ONLY:-0}" == "1" ]]; then
  echo "Validation only. Generated:"
  echo "  $FLY_CONFIG"
  echo "  $FLY_COMPOSE_FILE"
  exit 0
fi

if ! fly apps list --org "$FLY_ORG" --quiet | awk '{print $1}' | grep -qx "$COMPOSE_APP"; then
  fly apps create "$COMPOSE_APP" --org "$FLY_ORG" --yes
fi

fly deploy --config "$FLY_CONFIG" --ha=false
fly status --app "$COMPOSE_APP"

echo
echo "Public app URL:"
echo "  https://$COMPOSE_APP.fly.dev"
echo
echo "Test it with:"
echo "  ./scripts/03_test.sh https://$COMPOSE_APP.fly.dev"
