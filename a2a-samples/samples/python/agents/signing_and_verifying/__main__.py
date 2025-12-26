"""AgentCard 서명 에이전트 서버 진입점.

이 모듈은 AgentCard에 디지털 서명을 적용하는 A2A 에이전트 서버를 실행합니다.
ECDSA P-256 (ES256) 알고리즘을 사용하여 AgentCard의 무결성과 출처를 보장합니다.

주요 기능:
    - ECDSA P-256 키 쌍 동적 생성
    - 공개키를 JSON 파일로 저장하여 클라이언트가 검증에 사용
    - 공개 AgentCard와 확장 AgentCard 모두 서명
    - JWS(JSON Web Signature) 형식으로 서명 적용

실행 방법:
    python -m signing_and_verifying

서버 포트:
    기본 포트: 9999

엔드포인트:
    - /.well-known/agent.json: 서명된 공개 AgentCard
    - /agent/authenticatedExtendedCard: 서명된 확장 AgentCard
    - /public_keys.json: 서명 검증용 공개키

보안 흐름:
    1. 서버 시작 시 ECDSA P-256 키 쌍 생성
    2. 공개키를 public_keys.json 파일로 저장
    3. AgentCard 요청 시 개인키로 서명하여 반환
    4. 클라이언트는 /public_keys.json에서 공개키를 가져와 서명 검증
"""
import json

from pathlib import Path

import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from a2a.utils.signing import create_agent_card_signer
from agent_executor import (
    SignedAgentExecutor,
)
from cryptography.hazmat.primitives import asymmetric, serialization
from starlette.responses import FileResponse
from starlette.routing import Route


if __name__ == '__main__':
    # ECDSA P-256 개인키/공개키 쌍 생성
    # P-256(secp256r1)은 널리 사용되는 타원 곡선으로, ES256 알고리즘에 사용됩니다
    private_key = asymmetric.ec.generate_private_key(asymmetric.ec.SECP256R1())
    public_key = private_key.public_key()

    # 공개키를 PEM 형식으로 저장
    # 클라이언트가 이 파일을 가져와 AgentCard 서명을 검증합니다
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode('utf-8')
    kid = 'my-key'  # Key ID: 여러 키 중 이 키를 식별하는 ID
    keys = {kid: pem}
    with Path('public_keys.json').open('w') as f:
        json.dump(keys, f, indent=2)

    # 기본 스킬 정의
    skill = AgentSkill(
        id='reminder',
        name='Verification Reminder',
        description='Reminds the user to verify the Agent Card.',
        tags=['verify me'],
        examples=['Verify me!'],
    )

    # 확장 스킬 정의 (인증된 사용자에게만 제공)
    extended_skill = AgentSkill(
        id='reminder-please',
        name='Verification Reminder Please!',
        description='Politely reminds user to verify the Agent Card.',
        tags=['verify me', 'pretty please', 'extended'],
        examples=['Verify me, pretty please! :)', 'Please verify me.'],
    )

    # 공개 AgentCard 설정 (서명될 예정)
    public_agent_card = AgentCard(
        name='Signed Agent',
        description='An Agent that is signed',
        url='http://localhost:9999/',
        version='1.0.0',
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
        supports_authenticated_extended_card=True,
    )

    # 확장 AgentCard 설정 (공개 카드를 복사하고 스킬 추가)
    extended_agent_card = public_agent_card.model_copy(
        update={
            'name': 'Signed Agent - Extended Edition',
            'description': 'The full-featured signed agent for authenticated users.',
            'version': '1.0.1',
            'skills': [
                skill,
                extended_skill,  # 확장 카드에만 포함되는 추가 스킬
            ],
        }
    )

    # 요청 핸들러 설정
    request_handler = DefaultRequestHandler(
        agent_executor=SignedAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    # AgentCard 서명 함수 생성
    # JWS(JSON Web Signature) 형식으로 서명을 적용합니다
    signer = create_agent_card_signer(
        signing_key=private_key,
        protected_header={
            'kid': kid,  # Key ID: 어떤 키로 서명했는지 식별
            'alg': 'ES256',  # 알고리즘: ECDSA P-256
            'jku': 'http://localhost:9999/public_keys.json',  # 공개키를 조회할 URL
        },
    )

    # A2A 서버 애플리케이션 생성
    # card_modifier: 공개 AgentCard에 서명 적용
    # extended_card_modifier: 확장 AgentCard에 서명 적용
    server = A2AStarletteApplication(
        agent_card=public_agent_card,
        http_handler=request_handler,
        card_modifier=signer,  # 서명 함수로 공개 AgentCard 서명
        extended_agent_card=extended_agent_card,
        extended_card_modifier=lambda card, _: signer(
            card
        ),  # 확장 AgentCard도 같은 서명 함수 사용
    )

    app = server.build()

    # 공개키 파일을 제공하는 엔드포인트 추가
    # 클라이언트는 이 엔드포인트에서 공개키를 가져와 서명 검증에 사용합니다
    app.routes.append(
        Route(
            '/public_keys.json',
            endpoint=FileResponse('public_keys.json'),
            methods=['GET'],
        )
    )

    # uvicorn으로 서버 실행
    uvicorn.run(app, host='127.0.0.1', port=9999)
