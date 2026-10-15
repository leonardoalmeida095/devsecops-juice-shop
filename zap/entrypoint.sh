#!/bin/bash
set -u

TARGET_URL="${TARGET_URL:?TARGET_URL is required}"
GCS_BUCKET="${GCS_BUCKET:?GCS_BUCKET is required}"
REPORT_PREFIX="${REPORT_PREFIX:-zap/manual}"
ZAP_FAIL_ON="${ZAP_FAIL_ON:-HIGH}"

# O Automation Framework grava o relatório em /zap/wrk e trata o caminho
# como relativo. Um caminho absoluto vira /zap/wrk/zap/wrk/out/...
OUT=/zap/wrk/out
mkdir -p "$OUT"
cd /zap/wrk

echo "[1/3] DAST ZAP em ${TARGET_URL} (falha em ${ZAP_FAIL_ON})"
set +e
ARGS=(-t "$TARGET_URL" -m 1 -J out/report.json -r out/report.html -w out/report.md -x out/report.xml)
if [ "$ZAP_FAIL_ON" = "HIGH" ]; then
  ARGS+=(-I)
fi
/zap/zap-baseline.py "${ARGS[@]}"
ZAP_CODE=$?
set -e

echo "[2/3] Relatórios em ${OUT}"
ls -la "$OUT" || true

if compgen -G "$OUT/*" > /dev/null; then
  echo "[3/3] Upload gs://${GCS_BUCKET}/${REPORT_PREFIX}"
  python3 /zap/upload.py "$OUT" "$GCS_BUCKET" "$REPORT_PREFIX"
else
  echo "[3/3] ZAP não gerou relatório"
fi

if [ "$ZAP_FAIL_ON" = "HIGH" ] && [ "$ZAP_CODE" -eq 2 ]; then
  echo "Avisos médios não reprovam (ZAP_FAIL_ON=HIGH). ZAP_EXIT=${ZAP_CODE}"
  ZAP_CODE=0
fi

echo "ZAP_EXIT=${ZAP_CODE}"
if [ "$ZAP_CODE" -ne 0 ]; then
  echo "DAST reprovado"
  exit "$ZAP_CODE"
fi

if ! compgen -G "$OUT/*" > /dev/null; then
  echo "DAST sem relatório"
  exit 1
fi

echo "DAST aprovado"
exit 0
