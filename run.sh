#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

usage() {
  cat <<'HELP'
Uso: ./run.sh COMANDO [dev|prod]
  init                   Generar .env.dev y .env.prod sin sobrescribirlos
  build-dev | build-prod Construir la imagen
  up-dev | up-prod       Construir y arrancar; esperar healthchecks
  down [dev|prod]        Eliminar contenedores y redes; conservar volúmenes (dev por defecto)
  status [dev|prod]      Ver contenedores y salud
  logs [dev|prod]        Ver los últimos logs
  db-test [dev|prod]     Comprobar conexión SQL como usuario de la aplicación
  test [dev|prod]        Pruebas HTTP reales (crean una nota de prueba)
  verify [dev|prod]      Persistencia y caídas reales; recrea db conservando sus datos
  unit [dev|prod]        Pruebas unitarias dentro de la imagen web
  compose dev|prod ...   Ejecutar un comando Compose con la configuración correcta
  package               Crear dist/practica1.zip sin credenciales ni metadatos de Git
HELP
}

compose() {
  local environment="$1"
  shift
  case "$environment" in dev|prod) ;; *) echo 'Entorno válido: dev o prod' >&2; exit 2;; esac
  if [[ ! -f ".env.$environment" ]]; then
    echo 'Falta la configuración. Ejecuta ./run.sh init' >&2
    exit 1
  fi
  docker compose --project-name "practica1-$environment" \
    --env-file ".env.$environment" -f "docker-compose.$environment.yml" "$@"
}

action="${1:-help}"
case "$action" in
  init) python3 scripts/init_env.py ;;
  build-dev|build-prod) compose "${action#build-}" build ;;
  up-dev|up-prod) compose "${action#up-}" up --build -d --wait --wait-timeout 180 ;;
  down) compose "${2:-dev}" down --remove-orphans ;;
  status) compose "${2:-dev}" ps -a ;;
  logs) compose "${2:-dev}" logs --tail 100 ;;
  db-test)
    compose "${2:-dev}" exec -T db sh -c \
      'PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -U "$DB_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "SELECT current_user, current_database(), 1 AS connection_ok;"'
    ;;
  test)
    compose "${2:-dev}" exec -T web python - < scripts/smoke.py
    ;;
  verify) python3 scripts/verify.py "${2:-dev}" ;;
  unit)
    compose "${2:-dev}" run --rm --no-deps -T -v "$PWD/tests:/tests:ro" web \
      python -m unittest discover -s /tests -v
    ;;
  compose)
    [[ $# -ge 3 ]] || { usage; exit 2; }
    environment="$2"
    shift 2
    compose "$environment" "$@"
    ;;
  package) python3 scripts/package.py ;;
  help|-h|--help) usage ;;
  *) usage; exit 2 ;;
esac
