"""AgentCard 서명 검증 테스트 클라이언트.

이 모듈은 서명된 AgentCard의 검증 기능을 테스트하는 클라이언트입니다.
서버에서 AgentCard를 조회할 때 디지털 서명을 검증하여 무결성과 출처를 확인합니다.

주요 기능:
    - 서명된 공개 AgentCard 조회 및 검증
    - 서명된 확장 AgentCard 조회 및 검증
    - JWK(JSON Web Key) URL을 통한 공개키 조회

실행 방법:
    python test_client.py

사전 조건:
    서명 에이전트 서버가 localhost:9999에서 실행 중이어야 합니다.

검증 흐름:
    1. AgentCard 조회 요청
    2. 서명의 JKU(JSON Key URL) 헤더에서 공개키 URL 추출
    3. 해당 URL에서 공개키 조회
    4. 공개키로 서명 검증
    5. 검증 성공 시 AgentCard 반환
"""
import logging

from typing import TYPE_CHECKING

import httpx

from a2a.client import A2ACardResolver
from a2a.client.client import ClientConfig
from a2a.client.client_factory import ClientFactory
from a2a.utils.constants import (
    AGENT_CARD_WELL_KNOWN_PATH,
    EXTENDED_AGENT_CARD_PATH,
)
from a2a.utils.signing import create_signature_verifier
from cryptography.hazmat.primitives import serialization
from jwt.api_jwk import PyJWK


if TYPE_CHECKING:
    from a2a.types import AgentCard


def _key_provider(kid: str | None, jku: str | None) -> PyJWK | str | bytes:
    """서명 검증에 사용할 공개키를 제공합니다.

    JKU(JSON Key URL)에서 공개키 목록을 조회하고, KID(Key ID)에 해당하는
    키를 반환합니다. 이 함수는 서명 검증기에 의해 호출됩니다.

    Args:
        kid: Key ID. 사용할 공개키를 식별합니다.
        jku: JSON Key URL. 공개키 목록을 조회할 URL입니다.

    Returns:
        공개키 객체. PEM 형식에서 로드된 키입니다.

    Raises:
        ValueError: kid나 jku가 없거나 해당 키를 찾을 수 없는 경우.
    """
    if not kid or not jku:
        print('kid 또는 jku가 누락되었습니다')
        raise ValueError

    # JKU에서 공개키 목록 조회
    response = httpx.get(jku)
    keys = response.json()

    # KID에 해당하는 키 찾기
    pem_data_str = keys.get(kid)
    if pem_data_str:
        pem_data = pem_data_str.encode('utf-8')
        return serialization.load_pem_public_key(pem_data)
    raise ValueError


# ES256 알고리즘을 지원하는 서명 검증기 생성
signature_verifier = create_signature_verifier(_key_provider, ['ES256'])


async def main() -> None:
    """테스트 클라이언트의 메인 함수.

    서명된 AgentCard를 조회하고 검증하는 전체 흐름을 테스트합니다.
    공개 카드와 확장 카드를 모두 조회하며, 각 단계에서 서명을 검증합니다.
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    base_url = 'http://localhost:9999'

    async with httpx.AsyncClient() as httpx_client:
        # A2ACardResolver 초기화
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=base_url,
        )

        # AgentCard 조회 및 검증, BaseClient 초기화
        final_agent_card_to_use: AgentCard | None = None

        try:
            logger.info(
                '공개 AgentCard 조회 시도: %s%s',
                base_url,
                AGENT_CARD_WELL_KNOWN_PATH,
            )
            # signature_verifier를 전달하여 AgentCard 조회 시 서명 검증
            public_card = await resolver.get_agent_card(
                signature_verifier=signature_verifier,
            )  # 서명 검증 후 AgentCard 반환
            logger.info('공개 AgentCard 조회 및 검증 성공:')
            logger.info(
                public_card.model_dump_json(indent=2, exclude_none=True)
            )
            final_agent_card_to_use = public_card
            logger.info(
                '\n클라이언트 초기화에 공개 AgentCard 사용 (기본값).'
            )

            # 확장 카드가 지원되는지 확인
            if public_card.supports_authenticated_extended_card:
                try:
                    logger.info(
                        '\n공개 카드가 인증된 확장 카드를 지원합니다. 조회 시도: %s%s',
                        base_url,
                        EXTENDED_AGENT_CARD_PATH,
                    )
                    # 더미 인증 헤더 설정
                    auth_headers_dict = {
                        'Authorization': 'Bearer dummy-token-for-extended-card'
                    }
                    # 확장 카드도 서명 검증과 함께 조회
                    extended_card = await resolver.get_agent_card(
                        relative_card_path=EXTENDED_AGENT_CARD_PATH,
                        http_kwargs={'headers': auth_headers_dict},
                        signature_verifier=signature_verifier,
                    )  # 서명 검증 후 확장 AgentCard 반환
                    logger.info(
                        '인증된 확장 AgentCard 조회 및 검증 성공:'
                    )
                    logger.info(
                        extended_card.model_dump_json(
                            indent=2, exclude_none=True
                        )
                    )
                    final_agent_card_to_use = extended_card
                    logger.info(
                        '\n클라이언트 초기화에 인증된 확장 AgentCard 사용.'
                    )
                except (httpx.HTTPError, ValueError) as e_extended:
                    logger.warning(
                        '확장 AgentCard 조회 또는 검증 실패: %s. 공개 카드로 진행합니다.',
                        e_extended,
                        exc_info=True,
                    )
            elif public_card:
                logger.info(
                    '\n공개 카드가 확장 카드를 지원하지 않습니다. 공개 카드를 사용합니다.'
                )

        except Exception as e:
            logger.exception(
                '공개 AgentCard 조회 중 치명적 오류 발생.',
            )
            raise RuntimeError from e

        # ClientFactory를 사용하여 클라이언트 생성
        client_factory = ClientFactory(config=ClientConfig(streaming=False))

        # BaseClient 생성
        client = client_factory.create(final_agent_card_to_use)

        # 클라이언트를 통해 다시 카드 조회 (서명 검증 포함)
        get_card_response = await client.get_card(
            signature_verifier=signature_verifier
        )  # 서명 검증 후 AgentCard 반환
        print('다시 조회된 카드:')
        print(get_card_response.model_dump(mode='json', exclude_none=True))


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
