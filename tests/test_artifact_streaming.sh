#!/bin/bash

echo "🧪 A2A Artifact 스트리밍 테스트"
echo "================================"

# 긴 응답을 유도하는 테스트 요청 JSON
REQUEST_JSON=$(cat <<EOF
{
  "jsonrpc": "2.0",
  "id": "test-artifact-123",
  "method": "message/stream",
  "params": {
    "message": {
      "kind": "message",
      "messageId": "msg-artifact-456",
      "role": "user",
      "parts": [
        {
          "kind": "text",
          "text": "FastMCP의 주요 기능 5가지를 각각 2-3문장씩 설명해주세요."
        }
      ]
    }
  }
}
EOF
)

echo "📤 요청 전송 중..."
echo "$REQUEST_JSON" | jq .

echo -e "\n📥 스트리밍 응답 (Artifact 포함):"
echo "--------------------------------"

# 응답을 파일로 저장하면서 동시에 출력
RESPONSE_FILE="/tmp/a2a_streaming_response_$$.txt"

# SSE 스트리밍 요청
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d "$REQUEST_JSON" \
  --no-buffer \
  --max-time 60 \
  -w "\n\n⏱️ 총 소요 시간: %{time_total}초\n" 2>/dev/null | tee "$RESPONSE_FILE" | while IFS= read -r line; do
    if [[ $line == data:* ]]; then
        # data: 프리픽스 제거
        json_data="${line#data: }"
        
        # JSON 파싱 시도
        if echo "$json_data" | jq . >/dev/null 2>&1; then
            # kind 필드 확인
            kind=$(echo "$json_data" | jq -r '.result.kind // "unknown"' 2>/dev/null)
            
            if [[ "$kind" == "artifact-update" ]]; then
                # Artifact 업데이트인 경우
                artifact_id=$(echo "$json_data" | jq -r '.result.artifact.artifact_id // "unknown"' 2>/dev/null)
                append=$(echo "$json_data" | jq -r '.result.append // false' 2>/dev/null)
                last_chunk=$(echo "$json_data" | jq -r '.result.last_chunk // false' 2>/dev/null)
                text=$(echo "$json_data" | jq -r '.result.artifact.parts[0].text // ""' 2>/dev/null)
                
                echo "🎨 [Artifact Update]"
                echo "   ID: $artifact_id"
                echo "   Append: $append, Last: $last_chunk"
                echo "   Text: \"$text\""
                echo ""
            else
                # 다른 종류의 이벤트
                echo "📦 [$kind] 이벤트"
                echo "$json_data" | jq -c . 2>/dev/null || echo "$json_data"
                echo ""
            fi
        else
            # JSON이 아닌 경우
            if [[ -n "$json_data" && "$json_data" != "null" ]]; then
                echo "📝 Raw: $json_data"
            fi
        fi
    elif [[ -n "$line" ]]; then
        echo "$line"
    fi
done

echo "================================"

# Artifact 청크 수 분석
echo -e "\n📊 스트리밍 분석:"
ARTIFACT_COUNT=$(grep -c "artifact-update" "$RESPONSE_FILE" 2>/dev/null || echo 0)
echo "   - Artifact 청크 수: $ARTIFACT_COUNT"

# 청크별 append/last_chunk 분석
if [ $ARTIFACT_COUNT -gt 0 ]; then
    echo "   - 첫 번째 청크 append: $(grep -m1 '"append"' "$RESPONSE_FILE" | grep -o '"append":[^,}]*' | cut -d: -f2)"
    echo "   - 마지막 청크 last_chunk: $(grep '"last_chunk":true' "$RESPONSE_FILE" | tail -1 | wc -l | xargs)"
fi

# 임시 파일 삭제
rm -f "$RESPONSE_FILE"

echo "================================"
echo "✅ 테스트 완료"