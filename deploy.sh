#!/usr/bin/env bash
# deploy.sh — локальное развёртывание Thailand Railway Digital Twin на k3s
#
# Использование:
#   ./deploy.sh                        # обычный деплой / обновление
#   ./deploy.sh --clean-db             # очистить БД перед деплоем
#   ./deploy.sh --pull-images          # подтянуть образы из ghcr.io и импортировать в k3s
#   ./deploy.sh --pull-images --clean-db   # всё вместе

set -euo pipefail

REGISTRY="ghcr.io/raybotkin/railtwin"
SERVICES=(simulation frontend gateway raildatacollector raildbsetup)
K8S_DIR="$(cd "$(dirname "$0")/k8s" && pwd)"
NAMESPACE="railway"

CLEAN_DB=false
PULL_IMAGES=false

for arg in "$@"; do
  case $arg in
    --clean-db)    CLEAN_DB=true ;;
    --pull-images) PULL_IMAGES=true ;;
    *) echo "Неизвестный аргумент: $arg"; exit 1 ;;
  esac
done

##############################################################
# 1. Namespace
##############################################################
echo "==> Namespace..."
kubectl apply -f "$K8S_DIR/namespace.yaml"
kubectl apply -f "$K8S_DIR/network-policy.yaml"

##############################################################
# 2. imagePullSecret для ghcr.io
##############################################################
if ! kubectl get secret ghcr-registry-secret -n "$NAMESPACE" &>/dev/null; then
  if [[ -z "${GHCR_USER:-}" || -z "${GHCR_TOKEN:-}" ]]; then
    echo ""
    echo "==> imagePullSecret для ghcr.io не найден в кластере."
    echo "    Задайте переменные окружения GHCR_USER и GHCR_TOKEN,"
    echo "    или создайте секрет вручную:"
    echo "      kubectl create secret docker-registry ghcr-registry-secret \\"
    echo "        --docker-server=ghcr.io \\"
    echo "        --docker-username=<user> \\"
    echo "        --docker-password=<pat-token> \\"
    echo "        -n railway"
    echo ""
    echo "    Деплой продолжается — используются локально кэшированные образы."
  else
    echo "==> Создание imagePullSecret ghcr-registry-secret..."
    kubectl create secret docker-registry ghcr-registry-secret \
      --docker-server=ghcr.io \
      --docker-username="$GHCR_USER" \
      --docker-password="$GHCR_TOKEN" \
      -n "$NAMESPACE" \
      --dry-run=client -o yaml | kubectl apply -f -
  fi
else
  echo "==> imagePullSecret ghcr-registry-secret уже существует."
fi

##############################################################
# 3. Подтягивание образов из ghcr.io в k3s (опционально)
##############################################################
if [[ "$PULL_IMAGES" == "true" ]]; then
  if [[ -z "${GHCR_USER:-}" || -z "${GHCR_TOKEN:-}" ]]; then
    echo "ОШИБКА: GHCR_USER и GHCR_TOKEN должны быть заданы для --pull-images."
    exit 1
  fi
  echo "==> Аутентификация в ghcr.io..."
  echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin

  for svc in "${SERVICES[@]}"; do
    echo "==> Pulling $REGISTRY/$svc:latest ..."
    docker pull "$REGISTRY/$svc:latest"
    echo "==> Импорт $svc в k3s containerd..."
    docker save "$REGISTRY/$svc:latest" | k3s ctr images import -
  done
fi

##############################################################
# 4. Postgres + Redis
##############################################################
echo "==> Postgres..."
kubectl apply -f "$K8S_DIR/postgres/deployment.yaml"
kubectl apply -f "$K8S_DIR/postgres/service.yaml"

echo "==> Redis..."
kubectl apply -f "$K8S_DIR/redis/deployment.yaml"
kubectl apply -f "$K8S_DIR/redis/service.yaml"

##############################################################
# 5. Очистка БД (если запрошено)
##############################################################
if [[ "$CLEAN_DB" == "true" ]]; then
  echo ""
  echo "==> Очистка базы данных..."

  # Масштабируем зависимые сервисы до 0
  for svc in simulation raildatacollector raildbsetup; do
    if kubectl get deployment "$svc" -n "$NAMESPACE" &>/dev/null; then
      echo "    Остановка $svc..."
      kubectl scale deployment "$svc" -n "$NAMESPACE" --replicas=0 || true
    fi
  done

  # Удаляем postgres deployment и PVC
  echo "    Удаление postgres deployment..."
  kubectl delete deployment postgres -n "$NAMESPACE" --ignore-not-found=true
  echo "    Ожидание завершения pod..."
  kubectl wait --for=delete pod -l app.kubernetes.io/name=postgres -n "$NAMESPACE" \
    --timeout=60s 2>/dev/null || true

  echo "    Удаление postgres PVC..."
  kubectl delete pvc postgres-pvc -n "$NAMESPACE" --ignore-not-found=true

  # Пересоздаём postgres
  echo "    Создание чистого postgres..."
  kubectl apply -f "$K8S_DIR/postgres/deployment.yaml"
  kubectl apply -f "$K8S_DIR/postgres/service.yaml"
fi

##############################################################
# 6. Ожидание готовности Postgres
##############################################################
echo "==> Ожидание готовности Postgres..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=postgres \
  -n "$NAMESPACE" --timeout=120s

##############################################################
# 7. Secrets приложений
##############################################################
echo "==> Применение secrets..."

for manifest in \
  "$K8S_DIR/raildbsetup/secrets.yaml" \
  "$K8S_DIR/simulation/secrets.yaml" \
  "$K8S_DIR/raildatacollector/secrets.yaml"; do
  if [[ -f "$manifest" ]]; then
    kubectl apply -f "$manifest"
  else
    echo "    ВНИМАНИЕ: $manifest не найден, пропускаем."
    echo "    Скопируйте secrets.yaml.example → secrets.yaml и заполните значения."
  fi
done

##############################################################
# 8. raildbsetup (схема и seed-данные)
##############################################################
echo "==> raildbsetup..."
kubectl apply -f "$K8S_DIR/raildbsetup/configmap.yaml"
kubectl apply -f "$K8S_DIR/raildbsetup/deployment.yaml"
kubectl apply -f "$K8S_DIR/raildbsetup/service.yaml"

if [[ "$CLEAN_DB" == "true" ]]; then
  # После очистки БД нужно масштабировать обратно
  kubectl scale deployment raildbsetup -n "$NAMESPACE" --replicas=1
fi

echo "==> Ожидание готовности raildbsetup (может занять несколько минут)..."
kubectl rollout status deployment/raildbsetup -n "$NAMESPACE" --timeout=600s

##############################################################
# 9. Simulation, Gateway, Raildatacollector
##############################################################
echo "==> simulation..."
kubectl apply -f "$K8S_DIR/simulation/configmap.yaml"
kubectl apply -f "$K8S_DIR/simulation/deployment.yaml"
kubectl apply -f "$K8S_DIR/simulation/service.yaml"
kubectl apply -f "$K8S_DIR/simulation/hpa.yaml"

if [[ "$CLEAN_DB" == "true" ]]; then
  kubectl scale deployment simulation -n "$NAMESPACE" --replicas=1
fi

echo "==> gateway..."
kubectl apply -f "$K8S_DIR/gateway/configmap.yaml"
kubectl apply -f "$K8S_DIR/gateway/deployment.yaml"
kubectl apply -f "$K8S_DIR/gateway/service.yaml"

echo "==> raildatacollector..."
kubectl apply -f "$K8S_DIR/raildatacollector/configmap.yaml"
kubectl apply -f "$K8S_DIR/raildatacollector/deployment.yaml"
kubectl apply -f "$K8S_DIR/raildatacollector/service.yaml"

if [[ "$CLEAN_DB" == "true" ]]; then
  kubectl scale deployment raildatacollector -n "$NAMESPACE" --replicas=1
fi

##############################################################
# 10. Frontend + Ingress
##############################################################
echo "==> frontend..."
kubectl apply -f "$K8S_DIR/frontend/deployment.yaml"
kubectl apply -f "$K8S_DIR/frontend/service.yaml"
kubectl apply -f "$K8S_DIR/frontend/ingress.yaml"

##############################################################
# 11. Итоговый статус
##############################################################
echo ""
echo "==> Текущий статус подов:"
kubectl get pods -n "$NAMESPACE" -o wide

echo ""
echo "==> Деплой завершён."
echo ""
echo "    Для локального доступа:"
echo "      kubectl port-forward svc/frontend-service 3000:3000 -n railway &"
echo "      kubectl port-forward svc/gateway-service  8002:8002 -n railway &"
echo ""
echo "    Логи simulation:"
echo "      kubectl logs -f deployment/simulation -n railway"
