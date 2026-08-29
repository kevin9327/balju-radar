# 발주레이더 (Balju Radar)

**AI 교육·SW 구축 발주 리드 주간 리포트.** 기업 인사담당자·IT담당자·공공기관이 실무
커뮤니티에 직접 올린 발주 글만 골라 매주 정리해 발행합니다.

- 라이브: https://kevin9327.github.io/balju-radar/
- 발행: Petaflo AI Lab

## 원칙

- 리포트는 공개 게시글의 **제목·게시판·작성일 메타데이터와 원문 링크만** 담습니다.
- 게시글 본문을 복제하지 않고, **작성자 닉네임·개인 연락처는 수집·게재하지 않습니다.**
  제목에 연락처가 포함된 경우 자동 마스킹합니다.
- `[마감]`/`[취소]` 공고, 광고·후기·칼럼은 자동 제외합니다.

## 구조

```
tools/radar.py     수집(sweep) + 리포트 생성(build) 파이프라인
data/              수집 원시 데이터 (leads-YYYYMMDD.json)
reports/           발행된 주간 리포트 HTML
index.html         랜딩 페이지 (리포트 목록은 build가 자동 갱신)
```

## 실행

```bash
python tools/radar.py all --days 8    # 수집 + 리포트 + 목록 갱신
python tools/radar.py sweep --days 10 # 수집만
python tools/radar.py build           # 최신 수집분으로 리포트만
```

의존성 없음 (Python 3.9+ 표준 라이브러리만 사용).

## 발행 주기

매주 월요일 아침(KST) 발행. GitHub Actions(`.github/workflows/weekly.yml`)가
자동 수집·발행을 시도하고, 수집원 접근이 차단된 환경에서는 로컬에서
`tools/run_weekly.ps1`로 발행합니다.
