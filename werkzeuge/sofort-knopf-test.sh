#!/usr/bin/env bash
# Testet den Knopf "Trotzdem sofort spielen" (s:).
WEBHOOK=http://127.0.0.1:5678/webhook/DEIN-WEBHOOK-PFAD
echo "════ /wunsch benzin (legt den Plan an)"
curl -s -m 60 -o /dev/null -w "  HTTP %{http_code}\n" -X POST "$WEBHOOK" -H 'Content-Type: application/json' \
  -d '{"message":{"message_id":1,"chat":{"id":1,"type":"private"},"from":{"id":1,"first_name":"Test"},"text":"/wunsch benzin"}}'
echo "════ Knopf s: (Trotzdem sofort)"
curl -s -m 60 -o /dev/null -w "  HTTP %{http_code}\n" -X POST "$WEBHOOK" -H 'Content-Type: application/json' \
  -d '{"callback_query":{"id":"1","from":{"id":1,"first_name":"Test"},"data":"s:","message":{"message_id":3,"chat":{"id":1,"type":"private"}}}}'
