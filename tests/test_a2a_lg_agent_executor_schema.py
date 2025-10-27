"""
LangGraphWrappedA2AExecutor의 TypedDict/Annotated 스키마 처리 테스트

이 테스트는 다양한 스키마 타입(TypedDict, Annotated, 중첩 구조 등)에서
_get_graph_input_field_names() 메서드가 올바르게 필드명을 추출하는지 검증합니다.
"""
import os
import sys
import pytest

# tests가 repo 루트에서 실행될 때 src 패키지 경로를 포함하도록 설정
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.a2a_integration.a2a_lg_agent_executor import LangGraphWrappedA2AExecutor

# TypedDict / Annotated 호환성 처리
try:
    from typing import TypedDict, Annotated
except ImportError:
    # Python <3.9 또는 일부 환경
    from typing_extensions import TypedDict, Annotated


def _make_executor_for_schema(schema):
    """테스트용 더미 그래프를 생성하여 Executor를 반환."""
    class DummyGraph:
        def get_input_schema(self):
            return schema

    return LangGraphWrappedA2AExecutor(graph=DummyGraph())


class TestSimpleTypedDict:
    """단순 TypedDict 테스트"""

    def test_typedict_simple(self):
        """기본 TypedDict가 정상적으로 필드를 추출하는지 검증."""
        class SimpleTD(TypedDict):
            a: int
            b: str

        ex = _make_executor_for_schema(SimpleTD)
        result = ex._get_graph_input_field_names()
        assert result == {"a", "b"}, f"Expected {{'a', 'b'}}, got {result}"


class TestTypedDictWithAnnotatedFields:
    """Annotated 필드를 포함한 TypedDict 테스트"""

    def test_typedict_with_annotated_fields(self):
        """TypedDict 내부 필드가 Annotated로 래핑된 경우 정상 처리."""
        class TDAnnotatedFields(TypedDict):
            x: Annotated[int, "meta"]
            y: Annotated[str, "meta"]

        ex = _make_executor_for_schema(TDAnnotatedFields)
        result = ex._get_graph_input_field_names()
        assert result == {"x", "y"}, f"Expected {{'x', 'y'}}, got {result}"


class TestAnnotatedWrapperOverTypedDict:
    """Annotated로 래핑된 TypedDict 테스트"""

    def test_annotated_wrapper_over_typedict(self):
        """TypedDict 전체가 Annotated로 래핑된 경우 언랩 후 필드 추출."""
        class InnerTD(TypedDict):
            foo: int
            bar: str

        Schema = Annotated[InnerTD, "wrapper-meta"]
        ex = _make_executor_for_schema(Schema)
        result = ex._get_graph_input_field_names()
        assert result == {"foo", "bar"}, f"Expected {{'foo', 'bar'}}, got {result}"


class TestRootWrappedDict:
    """root dict로 래핑된 TypedDict 테스트"""

    def test_root_wrapped_dict_contains_typedict(self):
        """{'root': TypedDict} 형태에서 내부 TypedDict의 필드 추출."""
        class InnerTD2(TypedDict):
            u: int
            v: str

        schema = {"root": Annotated[InnerTD2, "meta"]}
        ex = _make_executor_for_schema(schema)
        result = ex._get_graph_input_field_names()
        assert result == {"u", "v"}, f"Expected {{'u', 'v'}}, got {result}"


class TestPlainDictSchema:
    """일반 dict 스키마 테스트"""

    def test_plain_dict_schema_keys_used(self):
        """일반 dict 스키마의 경우 키를 직접 필드명으로 사용."""
        schema = {"alpha": 1, "beta": "ok"}
        ex = _make_executor_for_schema(schema)
        result = ex._get_graph_input_field_names()
        assert result == {"alpha", "beta"}, f"Expected {{'alpha', 'beta'}}, got {result}"


class TestPydanticModel:
    """Pydantic 모델 호환성 테스트"""

    def test_pydantic_model_v2(self):
        """Pydantic v2 모델이 기존처럼 정상 작동하는지 검증."""
        try:
            from pydantic import BaseModel

            class MyModel(BaseModel):
                field1: str
                field2: int

            ex = _make_executor_for_schema(MyModel)
            result = ex._get_graph_input_field_names()
            assert result == {"field1", "field2"}, f"Expected {{'field1', 'field2'}}, got {result}"
        except ImportError:
            pytest.skip("Pydantic not installed")


class TestNestedTypedDict:
    """중첩 TypedDict 테스트"""

    def test_nested_typedict_fields(self):
        """TypedDict 내부에 다른 TypedDict 필드가 있어도 최상위 필드만 추출."""
        class NestedTD(TypedDict):
            inner_a: str

        class OuterTD(TypedDict):
            outer_field: int
            nested: NestedTD

        ex = _make_executor_for_schema(OuterTD)
        result = ex._get_graph_input_field_names()
        assert result == {"outer_field", "nested"}, f"Expected {{'outer_field', 'nested'}}, got {result}"


class TestEmptySchema:
    """빈 스키마 처리 테스트"""

    def test_none_schema(self):
        """스키마가 None인 경우 빈 집합 반환."""
        class DummyGraph:
            def get_input_schema(self):
                return None

        ex = LangGraphWrappedA2AExecutor(graph=DummyGraph())
        result = ex._get_graph_input_field_names()
        assert result == set(), f"Expected empty set, got {result}"

    def test_empty_typedict(self):
        """필드가 없는 TypedDict도 처리 가능."""
        class EmptyTD(TypedDict):
            pass

        ex = _make_executor_for_schema(EmptyTD)
        result = ex._get_graph_input_field_names()
        assert result == set(), f"Expected empty set, got {result}"


class TestComplexAnnotations:
    """복잡한 Annotated 구조 테스트"""

    def test_multiple_annotated_layers(self):
        """여러 단계의 Annotated 래핑도 처리."""
        class BaseTD(TypedDict):
            field_a: str
            field_b: int

        Schema = Annotated[Annotated[BaseTD, "meta1"], "meta2"]
        ex = _make_executor_for_schema(Schema)
        result = ex._get_graph_input_field_names()
        assert result == {"field_a", "field_b"}, f"Expected {{'field_a', 'field_b'}}, got {result}"


if __name__ == "__main__":
    # 개별 실행 시 pytest 호출
    pytest.main([__file__, "-v"])
