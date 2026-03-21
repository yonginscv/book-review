# 신문사 서평 수집 및 정리 프로젝트

최근 1주일 간의 주요 신문사 서평 기사를 수집하고, 책별로 내용을 요약하여 정리하는 자동화 도구입니다.

## 주요 기능 및 프로세스

1. **데이터 수집:** BigKinds API를 통해 최근 1주일간의 서평 기사를 페치합니다. 아래 "데이터 패치 방법" 을 참고하세요.
2. **수집 기사 저장:** 수집한 기사의 제목과 본문 내용을 `YYYY-MM-DD-기사.md` 포맷으로 저장합니다.
3. **정보 추출 및 요약:** OpenRouter API를 사용하여 기사 본문에서 책 제목, 저자, 핵심 내용을 추출하고 요약합니다.
4. **중복 제거 및 그룹화:** 동일한 도서에 대한 여러 신문사의 서평을 하나로 묶어 정리합니다.
5. **결과 저장:** `YYYY-MM-DD-서평.md` 포맷으로 저장합니다.

## 프롬프트 설계

### System Prompt

```text
당신은 신문 서평 전문 분석가입니다.
제공된 뉴스 기사 목록에서 서평 대상 도서를 식별하고, 도서별로 정보를 추출·요약합니다.
하나의 기사에 여러 도서가 소개될 수 있고, 동일한 도서가 여러 기사에 등장할 수 있습니다.
모든 출력은 한국어로 작성합니다.
```

### User Prompt 구조

기사 목록을 아래 형식으로 전달합니다. 기사 수가 많을 경우 토큰 절약을 위해 CONTENT의 HTML 태그(`<br/>` 등)를 미리 제거하고 전달합니다.

```text
다음은 최근 1주일간 수집된 신문 서평 기사입니다. 도서별로 정보를 추출하고 요약해주세요.

---
[기사 1]
신문사: {PROVIDER}
제목: {TITLE}
날짜: {DATE}
본문: {CONTENT (HTML 태그 제거)}

[기사 2]
...
---

## 요청사항

각 기사에서 언급된 도서를 모두 추출하고, 동일 도서는 하나로 묶어 아래 형식으로 출력하세요.

## 도서 제목

- **저자/역자:** (기사에 명시된 경우)
- **출판사:** (기사에 명시된 경우)
- **소개 신문사:** 동아일보 (2026-02-15), 조선일보 (2026-02-14)
- **핵심 내용:** 도서의 주제, 주요 내용, 구성을 3~5문장으로 요약
- **서평 관점:** 각 신문사가 이 책을 어떤 시각으로 바라보는지 간략히 정리. 비평적 견해나 추천 이유가 있으면 포함.
```

### 중복 도서 처리 규칙

- 도서 제목이 동일하면 반드시 하나의 항목으로 병합합니다.
- 병합 시 "소개 신문사" 항목에 모든 출처를 나열합니다.
- "서평 관점"에 신문사별 시각 차이가 있으면 구분하여 서술합니다.

## 기술 요구사항 및 구현 가이드

- **Language:** Python 3.11+
- **Library:** `requests` (Session 유지), `python-dotenv` (설정 관리), `tenacity` (재시도 로직)
- **세션 관리:** `requests.Session()`을 사용하여 쿠키(BigKinds, NCPVPCLBTG)를 모든 요청에서 공유합니다.
- **안정성:**
  - 기사 상세 페이지 호출 시 **5초 간격**의 지연 시간을 둡니다.
  - 네트워크 오류 시 최대 3회 재시도(Exponential Backoff)를 수행합니다.
- **설정 관리:** `.env` 파일을 통해 아래 값을 관리합니다.
  - `OPENROUTER_API_KEY`
  - `OPENROUTER_MODEL` (기본값: `google/gemini-2.0-flash-001`)
  - `RESULT_NUMBER` (기본값: 10)
  - `PROVIDER_CODES` (기본값: `["01100401", "01100801", "01101001", "02100101"]`)
- **AI 요약 전략:** 수집된 모든 기사를 하나의 요청으로 묶어 전달합니다(배치 처리). API 비용 절감을 위해 기사 본문의 HTML 태그를 제거한 뒤 전달합니다.

참고: OpenRouter API 호출 예시

```bash
curl https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -d '{
    "model": "google/gemini-2.0-flash-001",
    "messages": [
      {"role": "system", "content": "당신은 신문 서평 전문 분석가입니다. ..."},
      {"role": "user", "content": "..."}
    ]
  }'
```

## 데이터 페치 방법

### 1. cookie 값을 받아옵니다

www.bigkinds.or.kr 를 GET해서 Cookie 값을 받아옵니다. Set-Cookie에 BigKinds, NCPVPCLBTG 두개의 값이 중요합니다.

예. GET request

```bash
curl https://www.bigkinds.or.kr/
```

예. Get request응답

```txt
HTTP/1.1 200 OK
Date: Sun, 15 Feb 2026 12:04:34 GMT
Server: Apache
Set-Cookie: Bigkinds=736FCB499CC121658CB98D5921405318.tomcat2; Path=/; HttpOnly
Content-Language: en-US
Transfer-Encoding: chunked
Content-Type: text/html;charset=utf-8
Set-Cookie: NCPVPCLBTG=92e683b84841f9e922f49f830f2c66ac8c48ceb3f64b1797f3e88b1ccec63dc1; path=/
Cache-control: private
```

### 2. 기사들을 검색합니다.

기사 검색 URL은 https://www.bigkinds.or.kr/api/news/search.do 에 POST로 명령을 보냅니다. 

- 위 1. 에서 가져온 BigKinds, NCPVPCLBTG 값을 Cookie 헤더에 사용해주세요
- Accept, Accept-Language, Content-Type, Origin, Referer, User-Agent, X-Requested-With 헤더는 아래 예제의 값을 동일하게 사용
- POST body 는 아래 데이터를 사용해주고 startDate는 일주일 전, endDate는 오늘 날자를 사용하세요. 데이트 포맷은 YYYY-MM-DD 입니다.
- resultNumber 는 설정가능하도록 해주세요. default 값은 10
- 응답은 json 으로 오는데 resultList 의 NEWS_ID 들을 기억해서 다음 단계에 사용합니다.

```json
{"indexName":"news","searchKey":"(지음 OR  옮김)","searchKeys":[{"orKeywords":["지음, 옮김"]}],"byLine":"","searchFilterType":"1","searchScopeType":"1","searchSortType":"date","sortMethod":"date","mainTodayPersonYn":"","startDate":"2026-02-08","endDate":"2026-02-15","newsIds":[],"categoryCodes":[],"providerCodes":["01100401","01100801","01101001","02100101"],"incidentCodes":[],"networkNodeType":"","topicOrigin":"","dateCodes":[],"editorialIs":false,"startNo":1,"resultNumber":3,"isTmUsable":false,"isNotTmUsable":false}
```


POST 예제:

```bash
curl 'https://www.bigkinds.or.kr/api/news/search.do' \
  -H 'Accept: application/json, text/javascript, */*; q=0.01' \
  -H 'Accept-Language: en-US,en;q=0.9,ko;q=0.8,zh-TW;q=0.7,zh;q=0.6' \
  -H 'Content-Type: application/json;charset=UTF-8' \
  -b 'Bigkinds=736FCB499CC121658CB98D5921405318.tomcat2; NCPVPCLBTG=92e683b84841f9e922f49f830f2c66ac8c48ceb3f64b1797f3e88b1ccec63dc1' \
  -H 'Origin: https://www.bigkinds.or.kr' \
  -H 'Referer: https://www.bigkinds.or.kr/v2/news/search.do' \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36' \
  -H 'X-Requested-With: XMLHttpRequest' \
  --data-raw '{"indexName":"news","searchKey":"(지음 OR  옮김)","searchKeys":[{"orKeywords":["지음, 옮김"]}],"byLine":"","searchFilterType":"1","searchScopeType":"1","searchSortType":"date","sortMethod":"date","mainTodayPersonYn":"","startDate":"2026-02-08","endDate":"2026-02-15","newsIds":[],"categoryCodes":[],"providerCodes":["01100401","01100801","01101001","02100101"],"incidentCodes":[],"networkNodeType":"","topicOrigin":"","dateCodes":[],"editorialIs":false,"startNo":1,"resultNumber":3,"isTmUsable":false,"isNotTmUsable":false}'
```

응답 예제:

```json
{
  "getCategoryCodeList": [
    {
      "CategoryCode": "002000000",
      "CategoryCount": "1",
      "CategoryName": "경제"
    },
    {
      "CategoryCode": "003000000",
      "CategoryCount": "2",
      "CategoryName": "사회"
    },
    {
      "CategoryCode": "004000000",
      "CategoryCount": "27",
      "CategoryName": "문화"
    },
    {
      "CategoryCode": "005000000",
      "CategoryCount": "7",
      "CategoryName": "국제"
    },
    {
      "CategoryCode": "008000000",
      "CategoryCount": "1",
      "CategoryName": "IT_과학"
    }
  ],
  "documentCount": 3,
  "totalCntNotAnalysis": 1,
  "errorMessage": null,
  "errorCode": null,
  "totalCntAnalysis": 32,
  "totalCount": 33,
  "getDateCodeList": [
    {
      "date": "2026",
      "dateCount": "33"
    }
  ],
  "isLimitPage": false,
  "success": true,
  "getProviderCodeList": [
    {
      "ProviderName": "동아일보",
      "ProviderCount": "14",
      "ProviderCode": "01100401",
      "ProviderGubunCode": "10",
      "ProviderGubunName": "전국일간지"
    },
    {
      "ProviderName": "매일경제",
      "ProviderCount": "9",
      "ProviderCode": "02100101",
      "ProviderGubunCode": "20",
      "ProviderGubunName": "경제일간지"
    },
    {
      "ProviderName": "조선일보",
      "ProviderCount": "6",
      "ProviderCode": "01100801",
      "ProviderGubunCode": "10",
      "ProviderGubunName": "전국일간지"
    },
    {
      "ProviderName": "한겨레",
      "ProviderCount": "4",
      "ProviderCode": "01101001",
      "ProviderGubunCode": "10",
      "ProviderGubunName": "전국일간지"
    }
  ],
  "resultList": [
    {
      "CATEGORY_INCIDENT": "",
      "BYLINE": "이지윤",
      "byLine": "이지윤",
      "PROVIDER_SUBJECT": "0700",
      "IMAGES_CAPTION": "\n\n",
      "EXTENSION": "jpg",
      "CATEGORY_NAMES": "문화>출판<font color=Gray> | </font>문화>학술_문화재<font color=Gray> | </font>문화>생활",
      "CATEGORY_INCIDENT_NAMES": "",
      "PROVIDER_NEWS_ID": "20260215.133364360.2",
      "KPF_GABAGE_NEWS_IS": "FALSE",
      "printingPage": "",
      "DATE": "20260215",
      "PRINTING_PAGE": "",
      "NEWS_ID": "01100401.20260215060111001",
      "SUB_TITLE": "",
      "IMAGES": "https://www.bigkinds.or.kr/resources/images/01100401/2026/02/15/01100401.20260215060111001.01",
      "KPF_ABUSING_NEWS": "",
      "KPF_ABUSING_NEWS_IS": "FALSE",
      "CATEGORY": "004000000 004005000\n004000000 004010000\n004000000 004001000",
      "PROVIDER_LINK_PAGE": "https://www.donga.com/news/Culture/article/all/20260213/133364360/2",
      "PROVIDER": "동아일보",
      "TITLE": "한손엔 설 음식, 다른 손으로 ‘이 책’… 배부른 ‘4D 독서’ 어때요",
      "PROVIDER_CODE": "01100401",
      "CONTENT": "명절의 묘미는 상다리가 부러질 듯한 식탁이다. 색색깔 나물과 바삭한 전이 풍기는 구수한 향은 없던 입맛도 돌게 만든다. 짧지 않은 연휴, 최근 세계적으로도 열풍인 한식의 역사에 대해 알아볼 수 있는 책들을 읽어보면 어떨까. 지난해 1월 이후 출간된 도서 중에서 골라봤다. <br/> <br/>●한국인의 매운맛 사랑 <br/> <br/>‘매운맛’ 없이 오늘날 한국인의 입맛을 논하기 어.."
    },
    {
      "CATEGORY_INCIDENT": "",
      "BYLINE": "김유태 기자(ink@mk.co.kr)",
      "byLine": "김유태 기자(ink@mk.co.kr)",
      "PROVIDER_SUBJECT": "101103",
      "IMAGES_CAPTION": "파타고니아가 5년 전 올린 유튜브 다큐멘터리 영상 ‘Lessons from Jeju’의 한 장면. 임신 7개월차인 세계적인 다이버가 제주 해녀를 만나는 이야기를 담았다. [파타고니아 유튜브 캡처]\n",
      "EXTENSION": "png",
      "CATEGORY_NAMES": "문화>출판<font color=Gray> | </font>문화>미술_건축<font color=Gray> | </font>문화>방송_연예",
      "CATEGORY_INCIDENT_NAMES": "",
      "PROVIDER_NEWS_ID": "000011963468",
      "KPF_GABAGE_NEWS_IS": "FALSE",
      "printingPage": "",
      "DATE": "20260214",
      "PRINTING_PAGE": "",
      "NEWS_ID": "02100101.20260214154504001",
      "SUB_TITLE": "",
      "IMAGES": "https://www.bigkinds.or.kr/resources/images/02100101/2026/02/14/02100101.20260214154504001.01",
      "KPF_ABUSING_NEWS": "",
      "KPF_ABUSING_NEWS_IS": "FALSE",
      "CATEGORY": "004000000 004005000\n004000000 004006000\n004000000 004007000",
      "PROVIDER_LINK_PAGE": "http://www.mk.co.kr/article/11963468",
      "PROVIDER": "매일경제",
      "TITLE": "“당신에게 가장 기억에 남는 광고는?”...브랜드, 이미지가 살린다 [Book]",
      "PROVIDER_CODE": "02100101",
      "CONTENT": "제주해녀 다큐 만든 파타고니아 <br/>신혼 공감 일으킨 스위첸 광고 <br/> <br/>이미지·영상 익숙해진 사람들 <br/>강력한 한컷 있어야 제품 기억<br/><br/>5년 전 유튜브에 공개된 영상 ‘Lessons from Jeju’는 뜨거운 찬사를 이끌어냈다. 파타고니아가 다큐멘터리로 제작한 13분짜리 영상이었는데 제주 해녀에 대한 이야기다. 해녀 이야기란 단어만 보면 그리 새로울 것이 .."
    },
    {
      "CATEGORY_INCIDENT": "",
      "BYLINE": "정유정 기자(utoori@mk.co.kr)",
      "byLine": "정유정 기자(utoori@mk.co.kr)",
      "PROVIDER_SUBJECT": "101103",
      "IMAGES_CAPTION": "[Unspalsh/Rezal Scharfe]\n",
      "EXTENSION": "png",
      "CATEGORY_NAMES": "문화>생활<font color=Gray> | </font>문화>출판",
      "CATEGORY_INCIDENT_NAMES": "",
      "PROVIDER_NEWS_ID": "000011963435",
      "KPF_GABAGE_NEWS_IS": "FALSE",
      "printingPage": "",
      "DATE": "20260214",
      "PRINTING_PAGE": "",
      "NEWS_ID": "02100101.20260214133508001",
      "SUB_TITLE": "",
      "IMAGES": "https://www.bigkinds.or.kr/resources/images/02100101/2026/02/14/02100101.20260214133508001.01",
      "KPF_ABUSING_NEWS": "",
      "KPF_ABUSING_NEWS_IS": "FALSE",
      "CATEGORY": "004000000 004001000\n004000000 004005000",
      "PROVIDER_LINK_PAGE": "http://www.mk.co.kr/article/11963435",
      "PROVIDER": "매일경제",
      "TITLE": "“회사탈출은 지능순”…처세술 대신 재테크 책읽는 샐러리맨 [Book]",
      "PROVIDER_CODE": "02100101",
      "CONTENT": "샐러리맨의 탄생<br/><br/>오늘날 경제활동을 하는 사람 대부분은 어딘가에 소속되어 월급을 받는 샐러리맨이다. 익숙한 직장인의 모습 뒤에는 시대마다 미디어가 심어준 평범한 월급쟁이의 이미지가 투영돼 있다.<br/>다니하라 쓰카사 일본 리쓰메이칸대 교수의 신간 ‘샐러리맨의 탄생’은 일본 근현대사를 관통하며 샐러리맨이라는 존재가 어떻게 사회의 주류로 자리 잡았는지, 그리고 .."
    }
  ],
  "gubunCodeList": [
    "10",
    "20"
  ]
}
```

### 3. 기사의 값을 가져옵니다.

위 2단계 응답값의 resultList array의 NEWS_ID 마다 'GET https://www.bigkinds.or.kr/news/detailView.do?docId=${NEWS_ID}&returnCnt=1&sectionDiv=1000' 을 호출해서 기사 내용을 가져옵니다.

- (2단계외 동일) 위 1. 에서 가져온 BigKinds, NCPVPCLBTG 값을 Cookie 헤더에 사용해주세요
- (2단계외 동일) Accept, Accept-Language, Content-Type, Origin, Referer, User-Agent, X-Requested-With 헤더는 아래 예제의 값을 동일하게 사용
- 'GET https://www.bigkinds.or.kr/news/detailView.do?docId=${NEWS_ID}&returnCnt=1&sectionDiv=1000' 을 호출합니다. query parameter의 docId 값에 2의 resultList array의 NEWS_ID를 대입합니다. resultList array 마다 GET을 호출해서 기사 내용을 가져옵니다.
- 각 기사를 가져올 때 5초 간격을 줘서 rate limit에 걸리지 않토록 합니다.
- http 응답값의 detail.CONTENT 가 기사 내용입니다. 기사 마다 내용을 요약할 수 있도록 저장합니다.

```bash
curl 'https://www.bigkinds.or.kr/news/detailView.do?docId=01100401.20260215060111001&returnCnt=1&sectionDiv=1000' \
  -H 'Accept: application/json, text/javascript, */*; q=0.01' \
  -H 'Accept-Language: en-US,en;q=0.9,ko;q=0.8,zh-TW;q=0.7,zh;q=0.6' \
  -H 'Content-Type: application/json;charset=UTF-8' \
  -b 'Bigkinds=736FCB499CC121658CB98D5921405318.tomcat2; NCPVPCLBTG=92e683b84841f9e922f49f830f2c66ac8c48ceb3f64b1797f3e88b1ccec63dc1' \
  -H 'Origin: https://www.bigkinds.or.kr' \
  -H 'Referer: https://www.bigkinds.or.kr/v2/news/search.do' \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36' \
  -H 'X-Requested-With: XMLHttpRequest'
```

```json
{
  "ctx": "http://www.bigkinds.or.kr",
  "isStage": false,
  "domainName": "https://www.bigkinds.or.kr",
  "detail": {
    "BYLINE": "이지윤",
    "CATEGORY_CODE": "004000000 004005000\n004000000 004010000\n004000000 004001000",
    "CATEGORY_INCIDENT": "",
    "TMS_NE_LOCATION": "광화문\n식품영양학과\n평양\n서울\n신라\n강남\n함흥\n조선\n구미\n한국",
    "CATEGORY_MAIN": "문화>출판",
    "TMS_SIMILARITY": "조선^1.2578903 OR 매운맛^1.2225395 OR 허균^1.2047318 OR 도문대작^1.2012864 OR 냉면_노동자^1.1774964 OR 우리나라_냉면^1.1694739 OR 요즘_냉면^1.1466599 OR 냉면_사랑^1.1447725 OR 미식가^1.1360449 OR 매운맛_사랑^1.1218419 OR 강원대^1.1217356 OR 인문학^1.1216476 OR 노동자^1.121289 OR 19~20세기_냉면^1.1197659 OR 한국인^1.117638 OR 우리나라^1.1144855 OR 요즘_냉면_가게_전쟁^1.1141057 OR 1611년_조선^1.1081795 OR 조선시대_원조_미식가^1.1064812 OR 조선_팔도^1.1053537 OR 매운맛_향신료^1.1043806 OR 강원대_국어교육과_교수^1.1031305 OR 평양^1.1024116 OR 허균_연구자^1.101079 OR 문신_허균^1.0988781 OR 식품영양학과_교수^1.0972642 OR 조선시대_원조^1.0956225 OR 예능_열풍^1.0927533 OR 요리_서바이벌_예능_열풍^1.0922586 OR 미식가_선비^1.0878276 OR 면옥_노동자^1.087582 OR 강원대_국어교육과^1.0860366 OR 오늘날_한국인^1.0836796 OR 1925년_평양^1.0826268 OR 발대꾼^1.0816655 OR 발대^1.0816653 OR 산갓^1.0816497 OR 앞자리^1.0815691 OR 일제강점기^1.0815287 OR 시발점^1.0815282 OR 산갓김치^1.0814689 OR 상다리^1.0814307 OR 임금인상^1.0814182 OR 메밀국수^1.0812526 OR 강점기^1.0812414 OR 고명꾼^1.0812216 OR 반죽꾼^1.0812197 OR 고문헌^1.0812074 OR 색색깔_나물^1.0809717 OR 서울^1.0809346",
    "DATE": "20260215",
    "NEWS_ID": "01100401.20260215060111001",
    "SUB_TITLE": "",
    "TMS_NE_ORGANIZATION": "조선\n팔도\n강원대\n근현대",
    "IMAGES": "https://www.bigkinds.or.kr/resources/images/01100401/2026/02/15/01100401.20260215060111001.01.jpg,https://www.bigkinds.or.kr/resources/images/01100401/2026/02/15/01100401.20260215060111001.02.jpg,https://www.bigkinds.or.kr/resources/images/01100401/2026/02/15/01100401.20260215060111001.03.jpg",
    "CATEGORY_INCIDENT_MAIN": "",
    "TMS_NE_STREAM": "설:DT,한손:QT\n묘미:PR\n지난해 1월:DT\n오늘날:DT,한국:LC\n19세기:DT\n선사시대:DT,근현대:OG,신다연:PR,1611년:DT,조선:OG,문신:OC,허균:PS,1569~1618년:DT,허균#문신:PS_CLUE\n식품영양학과:LC,교수:OC,두 저자:QT,20세기:DT\n조선시대:DT\n16세기:DT,조선:LC,팔도:OG,선비:OC\n조선:OG\n이달:DT,65개:QT\n다채:PR,봄:DT\n강원대:OG,교수:OC\n구미:LC\n서울:LC,광화문:LC,강남:LC\n겨울:DT,구미:LC,함흥:LC,평양:LC\n신라:LC\n19~20세기:DT\n일제강점기:DT,1925년:DT,평양:LC,105명:QT,노동자:OC\n",
    "CATEGORY": "문화>출판<font color=Gray> | </font>문화>학술_문화재<font color=Gray> | </font>문화>생활",
    "TMS_RAW_STREAM": "김치,19세기,비평,조선시대_원조_미식가,고명꾼,포인트,구미,川椒醬,지도,세계적,혼탁,천초장,파업,전쟁,면옥,시작,재미_포인트,명절,지역,기록,일제,실마리,산초,진주냉면,역사,조상,젓갈,냉면_사랑,인상,매운맛,1569~1618년,빈도,강점기,식품영양학과_교수,목적,열망,발대,일제강점기,신라,선사시대,산갓김치,요리_서바이벌,광화문,마음,결성,20세기,미식가_선비,신다연_따비,배달부,저명,고추,서울_광화문,반죽꾼,경험,기원,재료,문신,우리나라,등장,1월,생선_웅어,정화,식재료,함흥냉면,초시,오늘날,고문헌,매력,숫자,매운맛_사랑,근현대,조합,확산,고등어_내장,1925년_평양,냉면_노동자,군침,겨울_구미,유형,입맛,16세기,국내,평양냉면,순행,압축,직장인,문신_허균,메밀국수,사용량,발대꾼,열풍,요리_서바이벌_예능_열풍,급속도,앞자리,얼음,음식,도문대작,허균_연구자,인문학적,4D_독서,촌철살인,임금인상,압도,이달_발간,한식,상다리,책들,강남,면옥_노동자,팔도,김풍기,초피,한국인,표현,친절,푸른역사,65개,진흥왕,고기,글항아리,자신,선조,평가,세속,105명,연휴,요즘_냉면,향신료,강명관,맛집_지도,조선_팔도,신라_진흥왕,요즘_냉면_가게_전쟁,사회,선조들,椒豉,외식,강원대_국어교육과_교수,저자,발길,식탁,매운맛_향신료,인기,시발점,별미,우리나라_냉면,본격적,이용,屠門大嚼,발자취,나물,1611년_조선,조상들,대목,양념,마늘,변천,19~20세기_냉면,통달,도서,남북,고추장,냉면들,출간,충족,색색깔_나물,묘미,오늘날_한국인,설명,정혜경",
    "TMS_SENTIMENT_CLASS": "",
    "PROVIDER_LINK_PAGE": "https://www.donga.com/news/Culture/article/all/20260213/133364360/2",
    "PROVIDER": "동아일보",
    "TITLE": "한손엔 설 음식, 다른 손으로 ‘이 책’… 배부른 ‘4D 독서’ 어때요",
    "PROVIDER_CODE": "01100401",
    "CONTENT": "명절의 묘미는 상다리가 부러질 듯한 식탁이다. 색색깔 나물과 바삭한 전이 풍기는 구수한 향은 없던 입맛도 돌게 만든다. 짧지 않은 연휴, 최근 세계적으로도 열풍인 한식의 역사에 대해 알아볼 수 있는 책들을 읽어보면 어떨까. 지난해 1월 이후 출간된 도서 중에서 골라봤다. <br/> <br/>●한국인의 매운맛 사랑 <br/> <br/>‘매운맛’ 없이 오늘날 한국인의 입맛을 논하기 어렵다. 그런데 우리나라에 고추가 본격적으로 사용되기 시작한 19세기 이전엔 어떻게 매운맛에 대한 열망을 충족할 수 있었을까. 선사시대부터 근현대에 이르는 우리 양념의 기원과 변천에 대해 짚은 책 ‘양념의 인문학’(정혜경, 신다연 지음·따비)은 1611년 조선의 문신 허균(1569~1618년)이 쓴 ‘도문대작(屠門大嚼)’에서 그 실마리를 찾는다. <br/> <br/>‘도문대작’에는 매운 장을 가리켜 ‘초시(椒豉)’라고 말하는 대목이 나온다. 책은 이를 고추장이 아닌, 초피로 만든 ‘천초장(川椒醬)’으로 본다. 식품영양학과 교수인 두 저자는 “매운맛을 좋아했던 우리 조상들은 고추 도입 이전에도 초피나 산초를 이용해 매운 양념을 만들어 먹었다”며 “20세기에 접어들면서 고추의 사용량과 빈도가 다른 매운맛 향신료를 압도하게 됐다”고 설명한다. <br/> <br/>●조선시대 원조 미식가 <br/> <br/>요리 서바이벌 예능 열풍이 거세다. 군침이 절로 나는 음식만큼이나 촌철살인 같은 평가가 재미 포인트다. 16세기에도 조선 팔도의 음식을 통달하고서 비평을 남긴 ‘미식가 선비’가 있었다. 앞서 ‘도문대작’을 쓴 허균이다. “남북을 오가며 맛난 고기든 아름다운 꽃부리든 씹어보지 않은 것이 없었다”는 그는 글에 자신이 경험한 조선의 맛과 멋을 압축시켰다. <br/> <br/>이달 발간된 책 ‘허균의 맛’(김풍기 지음·글항아리)은 ‘도문대작’을 “조선 최초의 맛집 지도”라고 평하면서 그 속에 담긴 65개의 음식을 인문학적으로 살핀다. 고소한 봄을 불러오는 생선 ‘웅어’부터 코가 뻥 뚫리는 산갓김치, 고등어 내장으로 만든 젓갈, “혼탁한 세속의 마음을 정화하는 재료”라고 표현한 마늘까지 다채로운 식재료가 등장한다. 강원대 국어교육과 교수이자 국내 저명한 허균 연구자가 풍부한 설명을 곁들여 친절하게 풀어썼다. <br/> <br/>●겨울 구미 당기는 냉면 <br/> <br/>직장인의 발길로 붐비는 서울 광화문과 강남 등은 요즘 냉면 가게 ‘전쟁’이다. 평양냉면, 함흥냉면, 진주냉면 등 지역마다 매력 있는 냉면들은 겨울에도 구미를 당기게 만든다. 책 ‘냉면의 역사’(강명관 지음·푸른역사)는 이처럼 다양한 우리나라 냉면의 발자취를 톺아본다. 신라 진흥왕이 순행 길에 얼음을 띄운 메밀국수를 먹었다는 기록을 시발점 삼아 여러 고문헌을 통해 선조들의 냉면 사랑을 살폈다. <br/> <br/>책의 ‘별미’는 19~20세기 냉면이 우리 사회에 급속도로 확산한 과정을 다룬 부분이다. 일제강점기인 1925년 평양에서는 105명의 면옥 노동자가 조합을 결성해 임금인상 등을 목적으로 파업을 일으켰다. 냉면이 외식으로 인기를 얻으면서 반죽꾼과 발대꾼, 앞자리, 고명꾼, 배달부 등 냉면 노동자의 유형도 숫자도 늘어난 데 따른 것으로 분석된다. <br/> <br/>이지윤 기자 leemail@donga.com",
    "TMS_NE_PERSON": "허균"
  },
  "lawsInfo": {
    "assTotal": 0,
    "lawTotal": 0
  }
}
```
