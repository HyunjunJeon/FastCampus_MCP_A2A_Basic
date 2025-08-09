#!/bin/bash

echo "🧪 스트리밍 테스트 (curl 사용)"
echo "================================"

# 테스트 요청 JSON
REQUEST_JSON=$(cat <<EOF
{
  "jsonrpc": "2.0",
  "id": "test-123",
  "method": "message/stream",
  "params": {
    "message": {
      "kind": "message",
      "messageId": "msg-456",
      "role": "user",
      "parts": [
        {
          "kind": "text",
          "text": "안녕하세요. 간단하게 답해주세요."
        }
      ]
    }
  }
}
EOF
)

echo "📤 요청 전송 중..."
echo "$REQUEST_JSON" | jq .

echo -e "\n📥 스트리밍 응답:"
echo "--------------------------------"

# SSE 스트리밍 요청
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d "$REQUEST_JSON" \
  --no-buffer \
  --max-time 30 \
  -w "\n\n⏱️ 총 소요 시간: %{time_total}초\n" 2>/dev/null | while IFS= read -r line; do
    if [[ $line == data:* ]]; then
        # data: 프리픽스 제거하고 출력
        echo "📦 청크: ${line#data: }"
    elif [[ -n $line ]]; then
        echo "$line"
    fi
done

echo "================================"
echo "✅ 테스트 완료"