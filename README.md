# BigKinds 서평 수집 및 AI 요약 자동화 (Newspaper Book Review Scraper & Summarizer)

최근 1주일간 주요 신문사에 실린 서평 기사를 자동으로 수집하고, OpenRouter(Gemini 2.0 등)를 활용하여 도서별로 핵심 내용을 요약·정리하는 도구입니다.

## 🚀 주요 기능

1.  **뉴스 데이터 수집**: BigKinds API를 통해 지정된 신문사의 최근 1주일 서평 기사를 페치합니다.
2.  **기사 본문 저장**: 수집된 기사의 원문 데이터를 `YYYY-MM-DD-기사.md` 형식으로 저장합니다.
3.  **AI 기반 요약**: OpenRouter API(기본 모델: `google/gemini-2.0-flash-001`)를 사용하여 기사에서 도서 정보(저자, 출판사, 핵심 내용, 서평 관점)를 추출합니다.
4.  **중복 제거 및 그룹화**: 서로 다른 신문사에서 다룬 동일 도서를 하나로 병합하여 일목요연하게 정리합니다.
5.  **최종 결과 생성**: 요약된 내용을 `YYYY-MM-DD-서평.md` 형식으로 저장합니다.

## 🛠 기술 스택

-   **Language**: Python 3.11+
-   **Libraries**: `requests`, `python-dotenv`, `tenacity` (재시도 로직)
-   **AI Platform**: OpenRouter (Google Gemini 2.0 Flash)
-   **Data Source**: [BigKinds (빅카인즈)](https://www.bigkinds.or.kr/)

## 📋 설치 및 설정

### 1. 저장소 클론 및 패키지 설치

```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정

프로젝트 루트 디렉토리에 `.env` 파일을 생성하고 아래 내용을 입력합니다.

```env
# OpenRouter API 키 (필수)
OPENROUTER_API_KEY=your_api_key_here

# 사용할 AI 모델 (선택 사항)
OPENROUTER_MODEL=google/gemini-2.0-flash-001

# 수집할 최대 기사 수 (선택 사항, 기본값: 10)
RESULT_NUMBER=10

# 수집 대상 신문사 코드 (선택 사항)
# 01100401: 동아일보, 01100801: 조선일보, 01101001: 한겨레, 02100101: 매일경제
PROVIDER_CODES=["01100401", "01100801", "01101001", "02100101"]
```

## 📖 사용 방법

아래 명령어를 실행하면 데이터 수집부터 AI 요약까지 전 과정이 자동으로 진행됩니다.

```bash
python main.py
```

or

```bash
python summarize.py 2026-04-25-기사.md custom-output.md  # 출력 경로 지정
```


### 프로세스 상세
- **Step 1**: BigKinds 세션 초기화 및 쿠키 획득
- **Step 2**: 검색 키워드(`(지음 OR 옮김)`) 기반 기사 검색
- **Step 3**: 기사별 상세 내용 수집 (Rate Limit 방지를 위해 기사당 5초 간격 유지)
- **Step 4**: 수집된 원문 기사 저장 (`YYYY-MM-DD-기사.md`)
- **Step 5**: AI 분석 요청 및 최종 서평 요약본 저장 (`YYYY-MM-DD-서평.md`)

## 📂 파일 구조

-   `main.py`: 메인 실행 스크립트
-   `instruction.md`: 프로젝트 설계 및 API 상세 가이드
-   `.env`: API 키 및 환경 설정 값
-   `requirements.txt`: 의존성 라이브러리 목록
-   `archive/`: 과거 수집/요약된 결과물 보관 폴더 (예시)

## ⚠️ 주의 사항

-   **Rate Limit**: BigKinds 서버 부하 방지를 위해 기사 상세 조회 시 5초의 지연 시간이 설정되어 있습니다.
-   **API 비용**: OpenRouter를 통해 외부 LLM을 호출하므로, 기사 본문이 매우 길 경우 토큰 사용량에 주의하세요. (본문 내 HTML 태그는 자동으로 제거 후 전달됩니다.)
