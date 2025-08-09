# Tavily Search API - Python 개발자 가이드

## 📋 목차

1. [개요](#개요)
2. [API 소개](#api-소개)
3. [Python SDK 설치 및 설정](#python-sdk-설치-및-설정)
4. [API 사용법](#api-사용법)
5. [API 매개변수 상세](#api-매개변수-상세)
6. [Best Practices](#best-practices)
7. [고급 사용법](#고급-사용법)
8. [에러 처리](#에러-처리)
9. [실제 사용 예제](#실제-사용-예제)

---

## 개요

### Tavily란?

- **AI 에이전트를 위한 첫 번째 전용 검색 엔진**
- LLM에 최적화된 실시간 웹 검색 API
- 전통적인 검색 API(Google, Serp, Bing)와 달리 AI 개발자와 자율 AI 에이전트에 특화
- 검색, 스크래핑, 필터링, 추출을 단일 API 호출로 처리

### 핵심 특징

- **목적 특화**: AI 에이전트와 LLM을 위해 특별히 설계
- **다양성**: 웹 검색, 뉴스, 학술 논문 등 다양한 소스 지원
- **성능**: 빠르고 효율적인 검색 결과 제공
- **통합 친화적**: 간단한 API로 쉬운 통합
- **투명성**: 상세한 메타데이터와 점수 시스템 제공

### 왜 Tavily를 선택해야 하는가?

- **RAG 최적화**: LLM 환각 문제 해결을 위한 정확한 컨텍스트 제공
- **시간 절약**: 스크래핑, 필터링, 최적화 작업을 자동화
- **고품질 결과**: AI 기반 점수 매기기 및 랭킹 시스템
- **크로스 에이전트 커뮤니케이션**: 짧은 답변 제공으로 에이전트 간 의사소통 지원

---

## API 소개

### Base URL

```
https://api.tavily.com
```

### 인증

- Bearer 토큰 인증 사용
- API 키는 `tvly-` 접두사로 시작
- 무료 계정: 월 1,000 API 크레딧 제공

### 주요 엔드포인트

- **POST /search**: 웹 검색 API
- **POST /extract**: 콘텐츠 추출 API  
- **POST /crawl**: 지능형 사이트 크롤링
- **POST /map**: 사이트맵 네비게이션

---

## Python SDK 설치 및 설정

### 설치

```bash
pip install tavily-python
```

### 기본 설정

```python
from tavily import TavilyClient, AsyncTavilyClient

# 동기 클라이언트
tavily_client = TavilyClient(api_key="tvly-YOUR_API_KEY")

# 비동기 클라이언트
async_client = AsyncTavilyClient(api_key="tvly-YOUR_API_KEY")
```

### API 키 관리

```python
import os
from tavily import TavilyClient

# 환경변수에서 읽기
api_key = os.getenv("TAVILY_API_KEY")
tavily_client = TavilyClient(api_key=api_key)
```

---

## API 사용법

### 1. 기본 검색

```python
from tavily import TavilyClient

tavily_client = TavilyClient(api_key="tvly-YOUR_API_KEY")
response = tavily_client.search("Who is Leo Messi?")
print(response)
```

### 2. 고급 검색 옵션

```python
response = tavily_client.search(
    query="AI trends 2024",
    search_depth="advanced",
    max_results=10,
    include_raw_content=True,
    topic="general"
)
```

### 3. 뉴스 검색

```python
response = tavily_client.search(
    query="latest AI developments",
    topic="news",
    days=7,
    max_results=5
)
```

### 4. 도메인 필터링

```python
response = tavily_client.search(
    query="Python machine learning tutorials",
    include_domains=["github.com", "stackoverflow.com", "medium.com"],
    exclude_domains=["ads.com", "spam.com"]
)
```

### 5. 콘텐츠 추출

```python
response = tavily_client.extract("https://en.wikipedia.org/wiki/Lionel_Messi")
print(response)
```

### 6. 사이트 크롤링

```python
response = tavily_client.crawl(
    "https://docs.tavily.com", 
    instructions="Find all pages on the Python SDK"
)
print(response)
```

---

## API 매개변수 상세

### 검색 매개변수

#### 필수 매개변수

- **query** (string): 검색 쿼리 (최대 400자)

#### 선택적 매개변수

**결과 제한**

- **max_results** (int, 기본값: 5): 반환할 최대 결과 수 (1-100)

**검색 깊이**

- **search_depth** (string, 기본값: "basic"):
  - `"basic"`: 빠른 검색, 기본 결과
  - `"advanced"`: 상세 검색, 더 많은 정보와 분석

**주제 필터**

- **topic** (string): 검색 주제
  - `"general"`: 일반 웹 검색
  - `"news"`: 뉴스 및 시사 정보
  - `"finance"`: 금융 및 경제 정보

**시간 필터**

- **time_range** (string): 검색 시간 범위
  - `"day"`: 최근 하루
  - `"week"`: 최근 일주일
  - `"month"`: 최근 한 달
  - `"year"`: 최근 일년
- **days** (int): 최근 며칠 이내 결과만 검색
- **start_date** (string): 검색 시작 날짜 (YYYY-MM-DD)
- **end_date** (string): 검색 종료 날짜 (YYYY-MM-DD)

**도메인 필터**

- **include_domains** (list): 포함할 도메인 리스트
- **exclude_domains** (list): 제외할 도메인 리스트

**콘텐츠 옵션**

- **include_raw_content** (bool, 기본값: false): 전체 추출 콘텐츠 포함
- **chunks_per_source** (int): 소스당 콘텐츠 청크 수

### 응답 형식

```json
{
  "query": "검색 쿼리",
  "answer": "AI가 생성한 짧은 답변",
  "images": ["이미지 URL 리스트"],
  "results": [
    {
      "title": "페이지 제목",
      "url": "페이지 URL", 
      "content": "콘텐츠 스니펫",
      "score": 0.81025416,
      "raw_content": "전체 콘텐츠 (옵션)",
      "favicon": "파비콘 URL",
      "published_date": "발행일 (뉴스의 경우)"
    }
  ],
  "auto_parameters": {
    "topic": "자동 감지된 주제",
    "search_depth": "사용된 검색 깊이"
  },
  "response_time": "응답 시간"
}
```

---

## Best Practices

### 1. 쿼리 최적화

#### 쿼리 길이 제한

```python
# ✅ 좋은 예 - 400자 이하
query = "AI trends in healthcare 2024"

# ❌ 나쁜 예 - 너무 긴 쿼리
query = "매우 긴 쿼리..." # 400자 초과 시 오류 발생
```

#### 복합 쿼리 분할

```python
# ✅ 좋은 예 - 서브 쿼리로 분할
queries = [
    "Competitors of company ABC",
    "Financial performance of company ABC", 
    "Recent developments of company ABC",
    "Latest industry trends related to ABC"
]

# ❌ 나쁜 예 - 모든 내용을 하나의 쿼리에
query = "Tell me about company ABC competitors financial performance recent developments and industry trends"
```

### 2. 매개변수 최적화

#### max_results 설정

```python
# ✅ 좋은 예 - 필요에 따라 결과 수 제한
response = tavily_client.search(
    query="renewable energy technologies",
    max_results=10  # 관련성과 포커스 향상
)

# ❌ 나쁜 예 - 불필요하게 많은 결과 요청
response = tavily_client.search(
    query="renewable energy technologies",
    max_results=50  # 너무 많은 결과
)
```

#### search_depth=advanced 활용

```python
# ✅ 좋은 예 - 높은 관련성이 필요할 때
response = tavily_client.search(
    query="How many countries use Monday.com?",
    search_depth="advanced",
    chunks_per_source=3,
    include_raw_content=True
)
```

#### 시간 필터링

```python
# ✅ 좋은 예 - 최신 정보가 중요할 때
response = tavily_client.search(
    query="latest trends in machine learning",
    time_range="month"
)
```

#### 뉴스 검색 최적화

```python
# ✅ 좋은 예 - 뉴스 소스에서 최신 정보
response = tavily_client.search(
    query="What happened today in NY?",
    topic="news",
    days=1
)
```

#### 도메인 필터링

```python
# ✅ 좋은 예 - 신뢰할 수 있는 도메인으로 제한
response = tavily_client.search(
    query="What is the professional background of the CEO at Google?",
    include_domains=["linkedin.com/in"]
)

# ✅ 좋은 예 - 관련성 높은 소수의 도메인
response = tavily_client.search(
    query="What are the latest funding rounds for AI startups?",
    include_domains=["crunchbase.com", "techcrunch.com", "pitchbook.com"]
)

# ❌ 나쁜 예 - 너무 많은 도메인
response = tavily_client.search(
    query="AI news",
    include_domains=["techcrunch.com", "wired.com", "verge.com", "ars-technica.com", 
                    "zdnet.com", "cnet.com", "engadget.com"]  # 너무 많음
)
```

### 3. 비동기 API 호출

```python
import asyncio
from tavily import AsyncTavilyClient

# 클라이언트 초기화 (한 번만)
tavily_client = AsyncTavilyClient("tvly-YOUR_API_KEY")

async def fetch_and_gather():
    queries = ["latest AI trends", "future of quantum computing"]
    
    # 동시 검색 수행 (예외 처리 포함)
    try:
        responses = await asyncio.gather(
            *(tavily_client.search(q) for q in queries), 
            return_exceptions=True
        )
        
        # 응답 처리
        for response in responses:
            if isinstance(response, Exception):
                print(f"Search query failed: {response}")
            else:
                print(response)
                
    except Exception as e:
        print(f"Error during search queries: {e}")

# 실행
asyncio.run(fetch_and_gather())
```

### 4. 후처리 기법

#### 점수 기반 필터링

```python
def filter_by_score(results, min_score=0.7):
    """관련성 점수로 결과 필터링"""
    return [result for result in results if result.get('score', 0) >= min_score]

response = tavily_client.search("Python machine learning")
filtered_results = filter_by_score(response['results'], min_score=0.8)
```

#### 키워드 필터링

```python
import re

def keyword_filter(results, required_keywords, excluded_keywords):
    """키워드 기반 필터링"""
    filtered = []
    for result in results:
        content = result.get('content', '') + ' ' + result.get('title', '')
        
        # 필수 키워드 확인
        has_required = all(
            re.search(keyword, content, re.IGNORECASE) 
            for keyword in required_keywords
        )
        
        # 제외 키워드 확인
        has_excluded = any(
            re.search(keyword, content, re.IGNORECASE) 
            for keyword in excluded_keywords
        )
        
        if has_required and not has_excluded:
            filtered.append(result)
    
    return filtered

# 사용 예
results = response['results']
filtered = keyword_filter(
    results, 
    required_keywords=['python', 'machine learning'],
    excluded_keywords=['advertisement', 'spam']
)
```

#### 정규 표현식을 이용한 데이터 추출

```python
import re

def extract_emails(text):
    """이메일 주소 추출"""
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return re.findall(pattern, text)

def extract_dates(text):
    """날짜 추출"""
    pattern = r'\d{4}-\d{2}-\d{2}'
    return re.findall(pattern, text)

# 사용 예
for result in response['results']:
    if result.get('raw_content'):
        emails = extract_emails(result['raw_content'])
        dates = extract_dates(result['raw_content'])
        print(f"Found emails: {emails}")
        print(f"Found dates: {dates}")
```

---

## 고급 사용법

### 1. 2단계 프로세스: 검색 → 추출

```python
def search_then_extract(query, max_urls=3):
    """검색 후 상위 결과에서 콘텐츠 추출"""
    
    # 1단계: 관련 URL 검색
    search_response = tavily_client.search(
        query=query,
        max_results=max_urls,
        search_depth="advanced"
    )
    
    # 2단계: 각 URL에서 상세 콘텐츠 추출
    extracted_contents = []
    for result in search_response['results']:
        url = result['url']
        try:
            extract_response = tavily_client.extract(url)
            extracted_contents.append({
                'url': url,
                'title': result['title'],
                'content': extract_response,
                'score': result['score']
            })
        except Exception as e:
            print(f"Failed to extract from {url}: {e}")
    
    return extracted_contents

# 사용 예
detailed_results = search_then_extract("Python asyncio tutorial", max_urls=5)
```

### 2. 지역별 검색

```python
# 미국 웹사이트로 제한
response = tavily_client.search(
    query="latest AI research",
    include_domains=["*.com"]
)

# 특정 국가 제외
response = tavily_client.search(
    query="global economic trends",
    exclude_domains=["*.is"]  # 아이슬란드 사이트 제외
)

# 도메인 조합
response = tavily_client.search(
    query="AI industry news",
    include_domains=["*.com"],
    exclude_domains=["example.com"]
)
```

### 3. 배치 처리

```python
import asyncio
from typing import List, Dict

class TavilyBatchProcessor:
    def __init__(self, api_key: str, max_concurrent=5):
        self.client = AsyncTavilyClient(api_key)
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_query(self, query: str, **kwargs) -> Dict:
        """단일 쿼리 처리"""
        async with self.semaphore:
            try:
                result = await self.client.search(query, **kwargs)
                return {"query": query, "result": result, "success": True}
            except Exception as e:
                return {"query": query, "error": str(e), "success": False}
    
    async def process_batch(self, queries: List[str], **kwargs) -> List[Dict]:
        """배치 쿼리 처리"""
        tasks = [self.process_query(query, **kwargs) for query in queries]
        return await asyncio.gather(*tasks)

# 사용 예
async def main():
    processor = TavilyBatchProcessor("tvly-YOUR_API_KEY")
    
    queries = [
        "Python machine learning libraries",
        "JavaScript frameworks 2024",
        "Cloud computing trends",
        "Cybersecurity best practices"
    ]
    
    results = await processor.process_batch(queries, max_results=5)
    
    for result in results:
        if result['success']:
            print(f"Query: {result['query']}")
            print(f"Results: {len(result['result']['results'])}")
        else:
            print(f"Failed query: {result['query']}, Error: {result['error']}")

# 실행
asyncio.run(main())
```

---

## 에러 처리

### 일반적인 에러와 해결책

```python
from tavily import TavilyClient
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def robust_search(query: str, max_retries=3, **kwargs):
    """견고한 검색 함수"""
    tavily_client = TavilyClient(api_key="tvly-YOUR_API_KEY")
    
    for attempt in range(max_retries):
        try:
            # 쿼리 길이 확인
            if len(query) > 400:
                raise ValueError("Query too long. Max length is 400 characters.")
            
            response = tavily_client.search(query, **kwargs)
            logger.info(f"Search successful for query: {query[:50]}...")
            return response
            
        except ValueError as e:
            logger.error(f"Invalid query: {e}")
            # 쿼리 단축 시도
            if "too long" in str(e):
                query = query[:350] + "..."
                continue
            else:
                raise
                
        except Exception as e:
            logger.warning(f"Search attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                logger.error(f"All {max_retries} attempts failed for query: {query}")
                raise
            
            # 재시도 전 잠시 대기
            import time
            time.sleep(2 ** attempt)  # 지수 백오프

# 사용 예
try:
    result = robust_search("very long query that might exceed the limit...")
except Exception as e:
    print(f"Search failed: {e}")
```

### HTTP 에러 처리

```python
def handle_api_errors(response_code: int, response_body: str):
    """API 에러 코드별 처리"""
    error_messages = {
        400: "잘못된 요청: 쿼리나 매개변수를 확인하세요",
        401: "인증 실패: API 키를 확인하세요", 
        429: "요청 한도 초과: 잠시 후 다시 시도하세요",
        432: "요청 길이 초과: 쿼리나 매개변수를 줄이세요",
        433: "매개변수 오류: 매개변수 값을 확인하세요",
        500: "서버 오류: 잠시 후 다시 시도하세요"
    }
    
    if response_code in error_messages:
        return error_messages[response_code]
    else:
        return f"알 수 없는 에러 ({response_code}): {response_body}"
```

---

## 실제 사용 예제

### 1. 뉴스 모니터링 시스템

```python
import asyncio
from datetime import datetime
from tavily import AsyncTavilyClient

class NewsMonitor:
    def __init__(self, api_key: str):
        self.client = AsyncTavilyClient(api_key)
        self.keywords = ["AI", "machine learning", "cryptocurrency", "climate change"]
    
    async def get_daily_news(self, keyword: str) -> dict:
        """특정 키워드의 일일 뉴스 수집"""
        try:
            response = await self.client.search(
                query=f"{keyword} news today",
                topic="news",
                days=1,
                max_results=10,
                search_depth="advanced"
            )
            return {
                "keyword": keyword,
                "timestamp": datetime.now().isoformat(),
                "news_count": len(response['results']),
                "news": response['results']
            }
        except Exception as e:
            return {
                "keyword": keyword,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def monitor_all_keywords(self):
        """모든 키워드 모니터링"""
        tasks = [self.get_daily_news(keyword) for keyword in self.keywords]
        results = await asyncio.gather(*tasks)
        
        return {
            "monitoring_date": datetime.now().date().isoformat(),
            "total_keywords": len(self.keywords),
            "results": results
        }

# 사용 예
async def run_news_monitor():
    monitor = NewsMonitor("tvly-YOUR_API_KEY")
    daily_report = await monitor.monitor_all_keywords()
    
    print(f"=== 뉴스 모니터링 리포트 ({daily_report['monitoring_date']}) ===")
    for result in daily_report['results']:
        if 'error' not in result:
            print(f"키워드: {result['keyword']}")
            print(f"뉴스 개수: {result['news_count']}")
            print("---")
        else:
            print(f"키워드 {result['keyword']} 처리 실패: {result['error']}")

asyncio.run(run_news_monitor())
```

### 2. 학술 연구 도우미

```python
class ResearchAssistant:
    def __init__(self, api_key: str):
        self.client = TavilyClient(api_key)
    
    def search_academic_sources(self, topic: str) -> dict:
        """학술 소스 검색"""
        academic_domains = [
            "arxiv.org",
            "scholar.google.com", 
            "pubmed.ncbi.nlm.nih.gov",
            "ieee.org",
            "acm.org",
            "springer.com",
            "nature.com",
            "science.org"
        ]
        
        response = self.client.search(
            query=f"{topic} research papers",
            include_domains=academic_domains,
            max_results=15,
            search_depth="advanced",
            include_raw_content=True
        )
        
        return self.process_academic_results(response, topic)
    
    def process_academic_results(self, response: dict, topic: str) -> dict:
        """학술 검색 결과 처리"""
        processed_results = []
        
        for result in response['results']:
            processed = {
                'title': result['title'],
                'url': result['url'],
                'relevance_score': result['score'],
                'summary': result['content'],
                'domain': result['url'].split('/')[2],
                'is_high_quality': result['score'] > 0.8,
            }
            
            # 발행연도 추출 시도
            import re
            year_match = re.search(r'20\d{2}', result['content'] + result['title'])
            if year_match:
                processed['publication_year'] = year_match.group()
            
            processed_results.append(processed)
        
        # 점수순 정렬
        processed_results.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return {
            'topic': topic,
            'total_results': len(processed_results),
            'high_quality_count': sum(1 for r in processed_results if r['is_high_quality']),
            'results': processed_results
        }

# 사용 예
assistant = ResearchAssistant("tvly-YOUR_API_KEY")
research_data = assistant.search_academic_sources("quantum computing algorithms")

print(f"연구 주제: {research_data['topic']}")
print(f"총 결과: {research_data['total_results']}")
print(f"고품질 결과: {research_data['high_quality_count']}")

for i, result in enumerate(research_data['results'][:5], 1):
    print(f"\n{i}. {result['title']}")
    print(f"   점수: {result['relevance_score']:.3f}")
    print(f"   도메인: {result['domain']}")
    if 'publication_year' in result:
        print(f"   발행연도: {result['publication_year']}")
```

### 3. 콘텐츠 큐레이션 시스템

```python
class ContentCurator:
    def __init__(self, api_key: str):
        self.client = TavilyClient(api_key)
    
    def curate_tech_content(self, technologies: list, content_types: list) -> dict:
        """기술 관련 콘텐츠 큐레이션"""
        curated_content = {}
        
        for tech in technologies:
            tech_content = {}
            
            for content_type in content_types:
                query = f"{tech} {content_type}"
                
                # 콘텐츠 타입별 검색 설정
                search_params = self.get_search_params(content_type)
                search_params.update({
                    'query': query,
                    'max_results': 8,
                    'search_depth': 'advanced'
                })
                
                try:
                    response = self.client.search(**search_params)
                    tech_content[content_type] = self.filter_quality_content(
                        response['results']
                    )
                except Exception as e:
                    tech_content[content_type] = {'error': str(e)}
            
            curated_content[tech] = tech_content
        
        return curated_content
    
    def get_search_params(self, content_type: str) -> dict:
        """콘텐츠 타입별 검색 매개변수"""
        params_map = {
            'tutorials': {
                'include_domains': ['medium.com', 'dev.to', 'github.com', 'stackoverflow.com']
            },
            'news': {
                'topic': 'news',
                'time_range': 'week'
            },
            'documentation': {
                'include_domains': ['docs.*', '*.readthedocs.io', 'github.com']
            },
            'videos': {
                'include_domains': ['youtube.com', 'vimeo.com']
            }
        }
        return params_map.get(content_type, {})
    
    def filter_quality_content(self, results: list) -> list:
        """품질 기준으로 콘텐츠 필터링"""
        quality_threshold = 0.7
        filtered = [r for r in results if r.get('score', 0) >= quality_threshold]
        
        # 제목 길이와 내용 품질로 추가 필터링
        high_quality = []
        for result in filtered:
            title_words = len(result['title'].split())
            content_words = len(result['content'].split())
            
            if title_words >= 3 and content_words >= 20:
                high_quality.append({
                    'title': result['title'],
                    'url': result['url'],
                    'score': result['score'],
                    'summary': result['content'][:200] + '...',
                })
        
        return high_quality[:5]  # 상위 5개만 반환

# 사용 예
curator = ContentCurator("tvly-YOUR_API_KEY")

technologies = ['Python', 'JavaScript', 'Docker']
content_types = ['tutorials', 'news', 'documentation']

curated = curator.curate_tech_content(technologies, content_types)

for tech, content in curated.items():
    print(f"\n=== {tech} ===")
    for content_type, items in content.items():
        print(f"\n{content_type.title()}:")
        if 'error' in items:
            print(f"  오류: {items['error']}")
        else:
            for i, item in enumerate(items, 1):
                print(f"  {i}. {item['title']} (점수: {item['score']:.3f})")
```

---

## 요약 및 권장사항

### 핵심 사용 원칙

1. **쿼리를 간결하게 유지** (400자 이내)
2. **복합 검색은 여러 쿼리로 분할**
3. **적절한 매개변수 사용** (search_depth, topic, 도메인 필터)
4. **비동기 처리로 성능 향상**
5. **점수 기반 후처리로 품질 향상**

### 성능 최적화

- AsyncTavilyClient 사용으로 동시 요청 처리
- 적절한 동시성 제한 (5-10개 요청)
- 에러 처리와 재시도 로직 구현
- 캐싱으로 중복 요청 방지

### 보안 고려사항

- API 키를 환경변수로 관리
- 요청 로깅 시 민감 정보 제외
- 요청 한도 모니터링

### 추가 학습 자료

- [Tavily GitHub Repository](https://github.com/tavily-ai/tavily-python)
- [공식 문서](https://docs.tavily.com/documentation)
- [Community Forum](https://community.tavily.com/)
