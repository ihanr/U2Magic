#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this update as root."
    exit 1
fi
bundle_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
class_file="$bundle_dir/BOOT-INF/classes/com/khc/u2/Util/QbApiUtil.class"
compose_file=/opt/u2magic/docker-compose.yml
image_ref=$(docker inspect -f '{{.Config.Image}}' u2magic)
image_id=$(docker inspect -f '{{.Image}}' u2magic)
compose_dir=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' u2magic)
compose_service=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' u2magic)

if [ "$image_ref" != u2magic-codex:latest ] || [ "$compose_dir" != /opt/u2magic ] || [ "$compose_service" != u2magic ]; then
    echo "Deployment differs from the expected /opt/u2magic Compose installation; nothing changed."
    exit 1
fi
test -f "$compose_file"
test -f "$class_file"
command -v python3 >/dev/null
command -v curl >/dev/null
docker compose -f "$compose_file" config --services | grep -qx u2magic

stamp=$(date +%Y%m%d-%H%M%S)
backup_dir=$(mktemp -d "/opt/u2magic-qb-api-backup-${stamp}-XXXXXX")
chmod 700 "$backup_dir"
build_dir=$(mktemp -d /tmp/u2magic-qb-api-build-XXXXXX)
docker cp u2magic:/data/u2Magic/lib/app.jar "$backup_dir/container-app.jar"
backup_image="u2magic-before-qb-api:${stamp}"
docker image tag "$image_id" "$backup_image"
printf '%s\n' "$image_id" > "$backup_dir/original-image-id.txt"
python3 "$bundle_dir/patch_qb_api.py" "$backup_dir/container-app.jar" "$build_dir/app.jar" "$class_file"

# Keep the host's build input patched as well, so a future Compose build retains it.
host_jar=/opt/u2magic/app.jar
if [ -f "$host_jar" ]; then
    cp -a -- "$host_jar" "$backup_dir/host-app.jar"
    python3 "$bundle_dir/patch_qb_api.py" "$host_jar" "$build_dir/host-app.jar" "$class_file"
fi

# Reuse the current local image, avoiding any upstream image or configuration changes.
docker build --pull=false --network=none --build-arg "BASE_IMAGE=$backup_image" \
    -f "$bundle_dir/Dockerfile.qb-api-patch" -t "$image_ref" "$build_dir"
if [ -f "$build_dir/host-app.jar" ]; then
    cp -- "$build_dir/host-app.jar" "$host_jar"
fi

restore_previous() {
    echo "Restoring original image and host jar. Backup: $backup_dir"
    docker image tag "$image_id" "$image_ref"
    if [ -f "$backup_dir/host-app.jar" ]; then cp -a -- "$backup_dir/host-app.jar" "$host_jar"; fi
    docker compose -f "$compose_file" up -d --no-build --no-deps u2magic || true
}
if ! docker compose -f "$compose_file" up -d --no-build --no-deps u2magic; then
    restore_previous
    exit 1
fi
docker cp u2magic:/data/u2Magic/lib/app.jar "$backup_dir/deployed-app.jar"
python3 "$bundle_dir/patch_qb_api.py" --verify "$backup_dir/deployed-app.jar" "$class_file"
ready=false
for attempt in $(seq 1 20); do
    http_code=$(curl -s --max-time 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:18080/index.html || true)
    case "$http_code" in
        200|401|403) ready=true; break ;;
    esac
    sleep 2
done
if [ "$ready" != true ]; then
    echo "Web service did not become ready; rolling back."
    restore_previous
    exit 1
fi
echo "Patch deployed. Backup: $backup_dir"
docker inspect -f 'running={{.State.Running}} restartCount={{.RestartCount}}' u2magic
echo "Existing .env, runtime data, Compose file and log service were retained."
