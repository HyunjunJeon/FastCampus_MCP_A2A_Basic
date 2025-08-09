#!/bin/bash

echo "🧪 간단한 스트리밍 테스트"
echo "========================"

# 짧은 테스트 요청
REQUEST_JSON='{
  "jsonrpc": "2.0",
  "id": "simple-test",
  "method": "message/stream",
  "params": {
    "message": {
      "kind": "message",
      "messageId": "msg-simple",
      "role": "user",
      "parts": [{"kind": "text", "text": "안녕"}]
    }
  }
}'

echo "📤 요청:"
echo "$REQUEST_JSON" | jq -c .

echo -e "\n📥 응답:"
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d "$REQUEST_JSON" \
  --no-buffer \
  --max-time 10 \
  -v 2>&1 | grep -E "data:|< HTTP"

echo -e "\n✅ 완료"