# 한국투자증권 Open API 조사 메모 (3단계 준비)

출처: 한국투자증권 공식 예제 저장소 `koreainvestment/open-trading-api`(2026-10-28 커밋 3a9be59)의
`examples_llm` 예제. 아직 계약(harness.json)에 넣지 않은 초안이며, 구현 전에 KIS Developers 포털
문서와 다시 대조해야 한다. brief: "공식 문서와 다르면 구현을 멈추고 질문한다".

## 결정 사항 (2026-11-05)

- 증권사: 한국투자증권, QQQ 전용 계좌를 연다. 사용 가능 현금 = 주문가능금액(현재 구현 그대로).
- 배당·분할: 해외주식 기간별권리조회 API의 '확정' 값만 반영하고, 기존 멈춤 장치(분할 기록 없는 큰 가격 변화,
  보유 수량 불일치)를 유지한다.
- 운영 OS: Linux. brief의 macOS 운영과 launchd 언급은 4단계에서 systemd timer로 바꾼다.
- 3단계는 3a(모의투자 연결)와 3b(실계좌 LOC 주문)로 나눈다. 3b는 모의 운영을 확인한 뒤 연다.

## 서버와 공통 규칙

- 실전 `https://openapi.koreainvestment.com:9443`, 모의 `https://openapivts.koreainvestment.com:29443`
- 헤더: `content-type`, `authorization: Bearer <token>`, `appkey`, `appsecret`, `tr_id`, `custtype: P`, `tr_cont`(연속 조회)
- 응답 본문: `rt_cd`("0"이면 성공), `msg_cd`, `msg1`
- 토큰: `POST /oauth2/tokenP` 본문 `{grant_type: client_credentials, appkey, appsecret}` →
  `access_token`, `access_token_token_expired`. 유효 1일, 6시간 안에 다시 요청하면 같은 토큰, 발급 때 알림톡 발송.
  brief의 "분당 1회 발급 제한"은 예제에서 확인하지 못했다.
- hashkey: 예제 주석상 현재 필수 아님.
- 호출 간격: 예제는 실전 0.05~0.1초, 모의 0.5초씩 쉰다.

## 사용할 API

| 용도 | 경로 | 실전 TR | 모의 TR | 메모 |
|---|---|---|---|---|
| 미국 매수 | `POST /uapi/overseas-stock/v1/trading/order` | TTTT1002U | VTTT1002U | ORD_DVSN 00 지정가, 32 LOO, 34 LOC. 모의는 00만 |
| 체결 내역 | `GET /uapi/overseas-stock/v1/trading/inquire-ccnl` | TTTS3035R | VTTS3035R | 주문번호로 검색 불가. 모의는 대부분 필터가 '전체'만 가능 |
| 매수 가능 금액 | `GET /uapi/overseas-stock/v1/trading/inquire-psamount` | TTTS3007R | VTTS3007R | ovrs_ord_psbl_amt, ord_psbl_frcr_amt, max_ord_psbl_qty |
| 잔고 | `GET /uapi/overseas-stock/v1/trading/inquire-balance` | TTTS3012R | VTTS3012R | ovrs_pdno, ovrs_cblc_qty, ord_psbl_qty, pchs_avg_pric |
| 일봉 | `GET /uapi/overseas-price/v1/quotations/dailyprice` | HHDFS76240000 | 같은 TR | EXCD `NAS`, SYMB, GUBN 0(일), BYMD, MODP 0(수정주가 미반영). 응답 xymd, open, high, low, clos, tvol |
| 배당·분할 | `GET /uapi/overseas-price/v1/quotations/period-rights` | CTRGT011R | 예제에 없음 | RGHT_TYPE_CD 03 배당, 75 특별배당, 14 액면분할, 15 액면병합. dfnt_yn 확정 여부, stkp_dvdn_frcr_amt2 주당 배당, stck_alct_rt 주식 배정 비율 |
| 결제일 | CTOS5011R | | | 휴장일 달력이 아니라 결제일 조회이고 조기 폐장 시각이 없다. 거래일 달력은 CSV를 유지한다 |

- 주문 본문: CANO, ACNT_PRDT_CD, OVRS_EXCG_CD(`NASD`), PDNO(`QQQ`), ORD_QTY, OVRS_ORD_UNPR,
  CTAC_TLNO, MGCO_APTM_ODNO, SLL_TYPE(매수는 빈 값), ORD_SVR_DVSN_CD("0"), ORD_DVSN
- 체결 내역 응답: odno, ord_dt, pdno, sll_buy_dvsn_cd, ft_ord_qty, ft_ord_unpr3, ft_ccld_qty,
  ft_ccld_unpr3, ft_ccld_amt3, nccs_qty, prcs_stat_name, rjct_rson, ord_tmd
- 거래소 코드는 주문 `NASD`, 시세 `NAS`로 다르다(brief와 같음).

## 3단계 초안

- 3a: 토큰 발급·캐시(프로젝트 밖 사용자 전용 파일), 인증 오류 시 재발급 1회(동작 예시 14), 키를 로그·DB·알림에
  남기지 않음, 매수 가능 금액·잔고·체결 내역으로 Broker 인터페이스 구현, 모의 주문(VTTT1002U, 00 지정가),
  일봉·확정 권리 갱신, 주문 POST는 재시도하지 않음. 실계좌 주문은 계속 막아 둔다.
- 3b: 실계좌 LOC(TTTT1002U, 34). 첫 운영은 한도를 소액으로 낮춰 LOC 체결을 확인한다.
- 4단계: 텔레그램 Notifier, systemd timer, 운영 서버 설정.
- 기존 시나리오 중 live 단계 거부(SCN-GRD-006)와 어댑터 없음(SCN-GRD-007)은 3b에서 계약과 테스트를 함께 고쳐야 한다.

## 아직 확인할 것

- 토큰 발급 횟수 제한, 초당 호출 제한과 그 오류 코드
- 주문 응답 필드(주문번호 등)
- 권리조회 API의 모의 지원 여부. 지원하지 않으면 모의 단계에서는 멈춤 장치에만 의존한다.
- API 주문 수수료: 예전 Open API 안내에는 "매매수수료는 HTS 사용수수료와 동일하며, API 사용에 따른 별도
  이용료는 없음"이라고 되어 있다. 계좌 개설 때 해외주식 이벤트 수수료가 API 주문에도 적용되는지 고객센터에서 확인한다.
- 이 세션에서는 네트워크 정책 때문에 securities.koreainvestment.com, apiportal.koreainvestment.com,
  corp.tossinvest.com을 직접 열 수 없었다.
