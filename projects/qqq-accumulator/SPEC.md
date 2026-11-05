# QQQ 장기 적립 자동 매수 — 1~2단계: 백테스트·기준선, 주문 상태 관리와 FakeBroker

원본 요구: BRIEF.md

## 설계

# QQQ 장기 적립 자동 매수 — 1~2단계 설계

AGENTS.md: 프로젝트와 상위 디렉터리에 AGENTS.md가 없다(확인함). 따라서 적용되는 추가 지침은 없다.

## 0. 범위
- 포함: CSV 가져오기(일봉·달력·환율), 백테스트(기준선 + "종가 X달러 이하 전액 매수" 규칙), 채택 판정, 단발 `run`(대조→안전 장치→판단→주문 의도 기록→FakeBroker 전송→체결 대조), `status`, `adjust`, Broker/Notifier 인터페이스와 FakeBroker/FakeNotifier.
- 제외(다음 단계): 실제 증권사 어댑터, 텔레그램, OS 스케줄 등록, 동작 예시 14(토큰 재발급·키 로그 검사), 공유 계좌 예산 장부, R1·R2 지표, paper 통과 기준 판정(설정 키는 정의만 하고 이번 범위에서는 어떤 명령도 쓰지 않는다).
- 백테스트 전용 실험: ma_band 규칙(REQ-BT-004)은 "비쌀 때 팔고 쌀 때 다시 사면 주수가 늘어나는가"를 세금·수수료를 넣어 시뮬레이션만 한다. 운영 규칙으로 쓸 수 없고, 채택되더라도 운영에 넣으려면 사용자가 brief의 매도 제외를 먼저 바꿔야 한다.
- 영구 제외: 운영 매도(증권사 매도 함수 없음), 공매도, 신용·미수, 레버리지 ETF, QQQ 외 종목, 분봉, 웹 UI, 환전 자동화, 세금 신고, 상주 데몬, 메시지 큐, DB 서버, 판단 경로의 LLM·이미지 분석.
- 환경: Python ≥3.11, 표준 라이브러리만, unittest. 소스 `src/`, 테스트 `tests/`. 네트워크를 쓰지 않는다. SQLite는 STRICT 테이블을 지원하는 3.37 이상이어야 한다(미만이면 DB를 여는 명령은 종료 코드 2).

## 1. 수치 원칙(float 금지)
- 금액·수량·가격은 모두 `decimal.Decimal`이다. 설정은 `tomllib`의 `parse_float=Decimal`로 읽고, CSV 값은 문자열에서 바로 Decimal로 바꾼다. float는 지표 계산에서만 허용한다.
- 가정(사용자 확인 필요) 반올림 규칙:
  - 지정가 = 직전 종가 × (1 + 여유%/100), 0.01 단위 ROUND_HALF_UP.
  - 수량 = 주문 금액 ÷ (지정가 × (1 + 수수료%/100)) 내림. 소수점 미지원이면 정수, 지원이면 0.000001 단위.
  - 체결 대금 = 수량 × 체결가, 0.01 HALF_UP. 수수료 = 체결 대금 × 수수료%, 0.01 올림. 현금 차감 = 대금 + 수수료.
  - KRW 입금의 USD 환산 = KRW ÷ 환율 × (1 − 환전 비용%/100), 0.01 내림. 배당 입금 = 보유 주수 × 주당 배당 × (1 − 원천징수%/100), 0.01 내림.
  - 환산 주수 = 주수 + 현금 ÷ 마지막 원시 종가, 0.000001 내림. 평균 매입 단가 = 총 매입 비용(수수료 포함) ÷ 현재 보유 주수, 0.0001 HALF_UP. 보유 0이면 null.
- JSON 출력의 금액·수량은 Decimal 문자열이다. 테스트는 `Decimal(값)`으로 비교한다.

## 2. 설정 파일(TOML, `--config` 경로)
숫자 결정값은 필수이고 기본값이 없다. 명령이 쓰는 키가 없거나 형식이 틀리면(타입, 범위, 문자열 숫자 포함) 그 명령은 주문 없이 종료 코드 2로 끝난다. 쓰지 않는 키는 검사하지 않는다.

| 키 | 형식 | 사용하는 명령 |
|---|---|---|
| `stage` | "dry-run" / "paper" / "live". 없으면 "dry-run" | run |
| `paths.database`, `paths.halt_file` | 문자열 경로 | 모든 명령 / run |
| `deposit.cycle` | "monthly" 또는 "every_n_trading_days" | backtest, run(기준선일 때) |
| `deposit.day` (monthly) | 정수 1–31 | 위와 같음 |
| `deposit.n` (every_n) | 정수 ≥1 | 위와 같음 |
| `deposit.anchor_date` (every_n) | "YYYY-MM-DD" | run(기준선일 때)만 |
| `deposit.amount` | 숫자 >0 | backtest |
| `deposit.currency` | "KRW" / "USD" | backtest |
| `limits.per_order_usd`, `limits.monthly_usd` | 숫자 >0 | run |
| `costs.buy_fee_pct` | 숫자 0–100 | backtest, run |
| `costs.fx_cost_pct`, `costs.dividend_withholding_pct` | 숫자 0–100 | backtest |
| `order_window.start`, `order_window.end` | "HH:MM" 뉴욕 시각, start < end | run |
| `order.limit_margin_pct` | 숫자 ≥0 | backtest, run |
| `guard.abnormal_price_pct` | 숫자 >0 | run |
| `shares.fractional` | bool | backtest, run |
| `adoption.holdout_years`, `adoption.rolling_window_years` | 정수 ≥1 | backtest |
| `adoption.min_outperformance_pct`, `adoption.min_rolling_ratio_pct` | 숫자 ≥0 / 0–100 | backtest |
| `paper.clean_days_required` | 정수 ≥1 | (이번 범위 미사용) |
| `sell_sim.sell_fee_pct`, `sell_sim.capital_gains_tax_pct` | 숫자 0–100 | backtest(rules에 ma_band가 있을 때만) |
| `sell_sim.annual_exemption_usd` | 숫자 ≥0. 해외주식 양도소득 기본공제(연 250만 원)를 달러로 환산해 넣는다(가정) | 위와 같음 |
| `operating_rule` | 테이블 `{type="baseline"}` 또는 `{type="close_at_or_below", threshold_usd=숫자}`. 없으면 baseline | run |

키와 토큰은 환경 변수로만 받는다. 이번 범위에는 키를 쓰는 코드가 없다. 프로그램은 설정 파일에 쓰지 않으므로 단계를 올릴 수 없다.

## 3. 데이터 파일과 가져오기
`import-data --file CSV`는 헤더를 보고 종류를 정한다(가정). 헤더를 알 수 없으면 종료 코드 2.
- 달력: `date,is_open,close_time` (is_open은 `true`/`false`, close_time은 뉴욕 시각 "HH:MM"이고 휴장일은 비움). 날짜 중복이나 형식 오류가 있으면 거부.
- 일봉: `date,open,high,low,close,volume,split_factor,dividend`. 원시 가격이고, split_factor는 그날 효력이 생기는 분할 비율(평소 1, 2:1이면 2), dividend는 그날 기준 주당 배당금이다.
  - 거부 조건: 날짜 중복, 첫 날짜~마지막 날짜 사이 달력상 개장일 누락, open/high/low/close ≤0, split_factor ≤0, dividend <0, 형식 오류, (가정) 달력에 없는 날짜이거나 휴장일인 날짜의 봉, 달력이 범위를 덮지 않음. 그래서 달력을 먼저 가져와야 한다.
- 환율: `date,usd_krw` (>0, 중복 거부).
- 각 가져오기는 그 종류의 전체 스냅샷이다. 원자적으로 기존 스냅샷을 바꾸고 파일 바이트의 SHA-256을 기록한다. 거부되면 아무것도 바뀌지 않고 stderr에 이유를 쓰고 종료 코드 2로 끝난다. 이 명령은 zoneinfo를 쓰지 않는다.

## 4. 저장소
SQLite 파일 하나, `PRAGMA journal_mode=WAL`, 모든 테이블 STRICT. 테이블은 설정의 `paths.database` 경로에 처음 열 때 만든다. 개념 테이블: 일봉, 달력, 환율, 스냅샷(종류·해시), 주문(`UNIQUE(trade_date, rule_id)`), 체결, 보정(adjust), 분할 적용 기록, 실행 로그(사유), 알림 발송 기록(중복 방지), 고정 중단(halt).
주문 상태: `DRY_RUN`, `SENDING`, `SENT`, `FILLED`, `UNFILLED`, `UNKNOWN`, `NOT_PLACED`, `REJECTED`.
DB 보유 수량 = 체결 수량 합 + adjust 합, 그리고 분할 적용 때 곱한다.

## 5. 공개 API (`src.app`)
- `main(argv: list[str], *, broker: Broker | None = None, notifier: Notifier | None = None, now: datetime | None = None, tz_loader: Callable[[str], tzinfo] = zoneinfo.ZoneInfo, stdout=None, stderr=None) -> int`
  - 형식: `--config PATH <command>`. 명령은 `import-data --file F`, `backtest --rules F`, `run`, `status`, `adjust --shares N --reason TEXT`. 반환값이 종료 코드다. 인자 오류도 2다.
  - backtest·status는 JSON을 stdout에 쓴다. run은 RunResult를 JSON 한 줄로 stdout에 쓴다. `now`가 None이면 현재 시각을 쓴다.
- `load_config(path) -> Config`. 파일·TOML 오류는 `ConfigError`이고, 키별 검사는 명령이 요구할 때 `ConfigError`를 낸다. `Config.stage`가 있다.
- `Store.open(path) -> Store`. `insert_order_intent(trade_date: date, rule_id: str, quantity: Decimal, limit_price: Decimal, status: str) -> int`는 같은 (trade_date, rule_id)가 있으면 `DuplicateOrderError`를 낸다(DB UNIQUE 위반을 바꾼 것). `list_orders() -> list[OrderRecord]`(최신순, 필드 trade_date, rule_id, status, quantity, limit_price, broker_order_id, fill_price, fill_cost). `holdings() -> Decimal`. `close()`.
- `import_csv(store, path) -> ImportResult(kind, rows, sha256)`. 거부되면 `DataImportError`.
- `Bar(date, open, high, low, close, volume, split_factor, dividend)`, `Rule(id, type, threshold_usd | None)`, `BacktestSettings(deposit_cycle, deposit_day, deposit_n, deposit_amount, currency, buy_fee_pct, fx_cost_pct, withholding_pct, limit_margin_pct, fractional)`.
- `simulate(bars: list[Bar], rules: list[Rule], settings: BacktestSettings, fx_rates: dict[date, Decimal] | None = None) -> SimulationResult`
  - 기준선 `baseline`은 항상 포함되며 rules에 다시 넣지 않는다. 전제: bars는 날짜 오름차순이고 검증된 거래일 연속이다. KRW인데 입금일 환율이 없으면 `DataImportError`.
  - `result.metrics[rule_id] -> RuleMetrics(final_shares, cash_usd, equivalent_shares, total_deposit_usd, average_cost_usd, cash_waiting_days, unfilled_count, final_shares_diff_vs_baseline, equivalent_shares_diff_vs_baseline, sell_count, realized_gain_usd, tax_usd)`. 뒤의 세 값은 ma_band가 아니면 0이다. `BacktestSettings`에는 sell_fee_pct, capital_gains_tax_pct, annual_exemption_usd(기본 0)가 더 있다.
  - `result.decisions -> list[Decision(date, rule_id, quantity, limit_price, side="buy"|"sell")]`. sell은 ma_band에만 있다. 판단일(T) 순이며 수량 >0인 주문만 담는다.
- `evaluate_adoption(rule_eval_shares, baseline_eval_shares, rolling_pairs: list[tuple[Decimal, Decimal]], min_outperformance_pct, min_rolling_ratio_pct) -> AdoptionResult(adopted: bool, outperformance_pct: Decimal | None, rolling_ratio_pct: Decimal)`
- `run_backtest(store, rules_path, config) -> dict` (JSON 직렬화 가능, 7절).
- `compute_order(prev_close, limit_margin_pct, rule_amount, orderable_cash, per_order_limit, monthly_remaining, buy_fee_pct, fractional) -> OrderPlan(limit_price, quantity, amount, binding: str, reason: str | None)`. binding은 "RULE" / "CASH" / "PER_ORDER_LIMIT" / "MONTHLY_LIMIT"이다. 수량 0이면 reason이 붙는다: binding이 MONTHLY_LIMIT이면 "MONTHLY_LIMIT_REACHED", 아니면 "INSUFFICIENT_CASH".
- `is_in_order_window(now: datetime, window_start: time, window_end: time, close_time: time, tz_loader=zoneinfo.ZoneInfo) -> bool`. 전제: now는 aware datetime이다(naive면 ValueError).
- `run_once(config, store, *, broker: Broker | None, notifier: Notifier, now: datetime, tz_loader=zoneinfo.ZoneInfo) -> RunResult(exit_code: int, reasons: list[str], orders_sent: int)`.
- `get_status(store) -> dict`, `record_adjustment(store, shares: Decimal, reason: str)`. reason이 비었으면 ValueError, CLI에서는 2.
- `Broker`(Protocol, 매수 전용): `get_orderable_cash_usd() -> Decimal`, `get_position(symbol) -> Decimal`, `place_loc_buy(OrderRequest(client_order_id, symbol, trade_date, quantity, limit_price)) -> str`(broker_order_id), `list_orders(trade_date) -> list[BrokerOrder(broker_order_id, client_order_id, symbol, side, quantity, limit_price, trade_date, status: "OPEN"|"FILLED"|"UNFILLED"|"REJECTED", fill_price)]`. 예외는 `BrokerTimeout`, `BrokerRejected`, `BrokerError`. 매도 메서드는 없다.
- `FakeBroker(orderable_cash: Decimal, position: Decimal)`: 메모리에서 동작하고 네트워크가 없다. 접수하면 수량×지정가만큼 주문가능금액을 묶는다. 테스트 보조 기능: `settle_close(trade_date, close)`(종가 ≤ 지정가면 종가로 전량 체결해 포지션을 늘리고 현금에서 체결 대금을 빼며, 아니면 UNFILLED로 두고 묶인 금액을 푼다), `set_position(qty)`, `fail_next_place(mode)`(mode는 "timeout_after_accept" / "timeout_before_accept" / "reject"), `place_calls: int`(성공·실패와 관계없이 place 호출 수).
- `Notifier`(Protocol): `send(Notification(kind, trade_date, reason, text)) -> None`. kind는 "DAILY_SUMMARY" / "WARNING" / "SAFETY" / "ERROR"이다. `FakeNotifier(fail: bool = False)`는 `messages`에 기록하고, fail이면 `send`가 예외를 낸다.
- 지표는 봉 하나씩 `update(bar)`로 증분 갱신하는 상태 객체로 둔다. 운영과 백테스트가 같은 판단 함수(`decide(rule, indicator_state, bar, available_cash, is_deposit_day)`)를 쓴다. 내부 구성은 구현 재량이다.

## 6. 백테스트 의미
각 거래일 D마다 다음 순서로 처리한다.
1. split_factor ≠1이면 보유 주수와 미결 주문 수량에 비율을 곱하고(소수점 미지원이면 내림), 지정가는 비율로 나눈다(가정).
2. 전날 낸 LOC를 D 종가로 정산한다. 종가 ≤ 지정가면 고정 수량 전량을 종가에 체결하고, 아니면 미체결 1회를 센다.
3. 배당을 현금에 넣는다(1단계 이후 보유 주수 기준).
4. D가 입금일이면 입금한다.
5. 지표를 갱신한다.
6. 규칙마다 판단해 D+1 LOC를 만든다. 지정가는 D 종가 기준이고, 수량은 이때 고정되며, 주문 금액만큼 현금을 묶는다.

- ma_band(백테스트 전용 실험, REQ-BT-004): 규칙마다 ma_days일 단순 이동평균(SMA)을 5단계에서 증분 갱신한다. 분할일에는 창 안의 과거 종가를 비율로 나눠 현재 주식 기준으로 바꾼다. 판단(6단계):
  - 매도 뒤 재매수 대기 중이면: SMA가 준비됐고 종가 ≤ SMA×(1+rebuy_at_or_below_pct/100)이며 사용 가능 현금이 있으면 전액 매수. 대기 중에는 입금일에도 사지 않는다. 매수가 체결되면 대기가 끝난다.
  - 아니면: SMA가 준비됐고 보유 주수 >0이고 종가 ≥ SMA×(1+sell_above_pct/100)이면 보유 주수×sell_fraction_pct/100(소수점 미지원이면 내림)을 판다. 지정가는 D 종가×(1−지정가 여유)이고 D+1 종가 ≥ 지정가면 D+1 종가에 체결, 아니면 미체결 1회. 신호가 없으면 기준선처럼 입금일에 전액 매수한다.
  - 매도 체결: 대금(0.01 반올림) − 매도 수수료(올림)가 현금에 들어온다. 원가는 평균 원가(매수 수수료 포함)로 비례해 뺀다. 실현 손익을 그해 누계에 더하고, 미납 세금 = max(0, 누계 − annual_exemption_usd) × 세율(0.01 올림)로 다시 계산한다. 미납 세금은 사용 가능 현금에서 빠진다.
  - 새 해의 첫 봉(0단계)에서 전년 미납 세금을 현금에서 내고 누계를 0으로 돌린다. 시뮬레이션이 끝날 때 남은 미납 세금은 cash_usd에서 뺀다.
  - 가정: 세금은 달러 기준이며 환차손익, 다른 종목과의 손익 통산, 신고 시점(5월)은 반영하지 않는다. 운영(run)의 operating_rule로는 쓸 수 없고 Broker에 매도 메서드는 없다.
- 기준선: D가 입금일일 때 사용 가능 현금(묶이지 않은 현금) 전액. close_at_or_below: D의 원시 종가 ≤ threshold이고 사용 가능 현금이 있으면 전액. 백테스트에서는 안전 한도를 쓰지 않는다(가정).
- 입금일: monthly는 매월 day 이후 첫 거래일이고, 그달에 없으면 그달 마지막 거래일이다. every_n_trading_days는 시뮬레이션 첫 거래일과 그 뒤 n 거래일마다이다. 운영에서는 anchor_date부터 센다.
- 현금 대기 일수(가정): 6단계 뒤 묶이지 않은 현금 > 0인 거래일 수.
- 분할 조정 지표: 과거 가격을 현재 주식 기준으로 환산한 일간 종가 변화율. 분할일에 직전 종가 ÷ 비율과 비교한다. threshold 규칙은 현재 기준 원시 종가를 쓴다(가정).

## 7. backtest JSON
`{"data": {"bars_sha256", "calendar_sha256", "fx_sha256"|null}, "segments": {"tuning": {"start","end","rules": {id: metrics}}, "evaluation": {...}}, "rolling": {id: {"windows", "at_or_above_baseline", "ratio_pct"}}, "adoption": {id: {"adopted", "outperformance_pct", "rolling_ratio_pct"}}, "selected_rule": id}`
- 평가 구간은 날짜 > (마지막 봉 날짜 − holdout_years년)인 봉이다. 조정 구간은 그 앞 전체다. 구간마다 현금 0, 주식 0에서 따로 시뮬레이션한다.
- 롤링 창은 전체 데이터에서 매월 첫 거래일에 시작하고, 끝은 (시작 + N년 − 1일) 이하의 마지막 거래일이다. 끝이 마지막 봉 날짜를 넘는 창은 뺀다. 데이터가 holdout 또는 창 하나보다 짧으면 종료 코드 2.
- 채택(가정): 평가 구간 final_shares가 기준선보다 많고 (규칙−기준선)/기준선×100 ≥ min_outperformance_pct이다(기준선 0이면 규칙 >0이면 충족). 그리고 롤링 창 가운데 규칙 final_shares ≥ 기준선인 비율 ≥ min_rolling_ratio_pct이다. 채택된 규칙 중 평가 final_shares가 가장 큰 것(같으면 파일 순서)이 selected_rule이고, 없으면 "baseline"이다. 프로그램은 운영 규칙을 자동으로 바꾸지 않는다.
- rules 파일(JSON): `{"rules": [{"id": "le60", "type": "close_at_or_below", "threshold_usd": "60"}, {"id": "band", "type": "ma_band", "ma_days": 200, "sell_above_pct": "20", "sell_fraction_pct": "50", "rebuy_at_or_below_pct": "0"}]}`. 알 수 없는 type, id 중복, id "baseline", threshold ≤0이면 종료 코드 2. ma_band는 ma_days 정수 ≥2, sell_above_pct >0, 0 < sell_fraction_pct ≤ 100, −100 < rebuy_at_or_below_pct < sell_above_pct가 아니거나 sell_sim 설정이 없으면 종료 코드 2.

## 8. run 흐름 (`run_once`)
뉴욕 날짜 D = now를 America/New_York으로 바꾼 날짜. 판단 봉 T = D보다 이전인 봉 중 가장 최근 봉.
0. 시작 검사(종료 코드 2, 주문 0, ERROR 알림): tz_loader 실패(TIMEZONE_UNAVAILABLE), run이 쓰는 설정 오류(CONFIG_ERROR), stage가 live(STAGE_NOT_SUPPORTED, 이번 범위에서는 어떤 경우에도 실계좌 주문을 하지 않음), stage가 dry-run/paper인데 broker가 None(NO_BROKER_ADAPTER). CLI 기본값에는 어댑터가 없다. 그래서 주입 없이 실행한 `run`은 단계와 관계없이 2로 끝난다(가정: dry-run도 대조와 주문가능금액이 필요하기 때문).
1. 대조(항상 먼저 하고 읽기 전용):
   - 적용하지 않은 분할 봉(T 이하)이 있으면 DB 보유 수량에 비율을 곱한다.
   - SENDING/SENT/UNKNOWN 주문을 `list_orders(trade_date)`로 조회한다. client_order_id가 같은 주문, 없으면 (QQQ, BUY, 수량, 지정가)가 같은 미연결 주문에 연결한다. SENDING이 연결되면 SENT, 없으면 UNKNOWN으로 두고 재전송하지 않는다. FILLED·UNFILLED는 반영한다.
   - UNKNOWN은 그 거래일 마감 시각 이후 실행에서만 확정한다. 연결되면 반영하고, 연결되지 않고 증권사 보유 = DB 보유면 NOT_PLACED이다. 다르면 불일치로 처리한다.
   - 증권사 보유 ≠ DB 보유면 고정 중단 POSITION_MISMATCH를 기록한다. 이 중단은 이후 adjust가 기록되기 전까지 풀리지 않는다.
2. 일일 요약: 마감 시각이 지난 가장 최근 거래일 중 아직 요약을 보내지 않은 날에 DAILY_SUMMARY 1건(주문이 없는 날 포함)을 보낸다.
3. 사유 판정(처음 해당하는 것으로 끝남). 종료 코드는 괄호 안과 같다.
   - POSITION_MISMATCH(1), UNRESOLVED_ORDER: SENDING/UNKNOWN 미확정 주문이 있음(1), HALT_FILE(1), CALENDAR_MISSING: D가 달력에 없음(1), MARKET_CLOSED(0), OUTSIDE_WINDOW(0), ALREADY_ORDERED: (D, 운영 규칙) 주문 행이 이미 있음(0), STALE_BAR: T ≠ 달력상 D의 직전 거래일(1), ABNORMAL_PRICE: T 종가와 T 직전 봉 종가(분할 조정) 사이 변화율 절댓값이 abnormal_price_pct를 넘음(1), NO_SIGNAL(0).
4. 주문 금액은 min(규칙 금액, 주문가능금액, 1회 한도, 월 한도 잔액)이다. 월 한도 잔액 = monthly_usd − D가 속한 달의 (FILLED 체결 비용 + SENDING/SENT/UNKNOWN 주문의 수량×지정가)이다. MONTHLY_LIMIT_REACHED는 1이고 SAFETY 알림을 보낸다. INSUFFICIENT_CASH는 0이고 WARNING 알림을 보내며 주문 행을 만들지 않는다. 1회 한도가 결정값이면 PER_ORDER_LIMIT_APPLIED WARNING을 보내고 계속한다.
5. dry-run: 상태 DRY_RUN으로 기록하고 전송하지 않는다(DRY_RUN_RECORDED, 0). paper: SENDING으로 커밋한 뒤 place_loc_buy를 부른다. 성공하면 SENT + broker_order_id(ORDER_SENT, 0)이다. BrokerTimeout이면 SENDING을 그대로 두고 BROKER_TIMEOUT(2)이다. BrokerRejected이면 REJECTED, BROKER_ERROR(2)이다.
- 종료 코드 1인 사유는 SAFETY 알림, 2는 ERROR 알림을 즉시 보낸다. SAFETY/WARNING은 (뉴욕 날짜, 사유)당 1회만 보내고, ERROR는 매번 보낸다. 알림 예외는 잡아서 실행 로그에만 남기고, 주문 상태·종료 코드를 바꾸지 않는다. 모든 실행은 실행 로그에 사유를 남긴다.
- 주문 시간대: 뉴욕 시각 start ≤ t ≤ end. 조기 폐장일에는 (16:00 − 그날 마감 시각)만큼 앞당긴다(가정). 마감 시각 판정도 달력 close_time 기준이다.

## 9. status JSON
`{"shares", "average_cost_usd", "recent_orders": [최신 5건 {trade_date, rule_id, status, quantity, limit_price, fill_price}], "active_halts": [고정 중단 사유], "last_run": {"at", "exit_code", "reasons"}|null}`

## 10. 가정(사용자 확인 필요) 요약
1절 반올림, 3절 CSV 형식·헤더 판별·휴장일 봉 거부·달력 선행, 6절 ma_band 세금 모형(달러 기준·평균 원가·연간 공제·다음 해 첫 봉 납부), 6절 입금 주기 형식·백테스트 안전 한도 미적용·분할 시 미결 주문 조정·현금 대기 일수 정의·threshold는 원시 종가, 7절 구간·창·채택 판정식, 8절 CLI dry-run도 어댑터가 없어 2·사유 우선순위와 종료 코드(휴장·시간대 밖·이미 주문·신호 없음·현금 부족은 0)·알림 중복 방지·일일 요약 시점·조기 폐장 시간대 이동·월 한도 산식·dry-run 행은 월 한도에서 제외, 9절 최근 주문 5건.

## 11. 공통 운영 픽스처 F (시나리오가 참조)
- 달력: 2026-10-01~2026-12-31 평일은 개장하고 마감은 16:00이다. 단 2026-11-26은 휴장, 2026-11-27은 마감 13:00이다. 주말은 휴장이다. 2027년은 없다.
- 일봉: 2026-10-01~2026-11-04 모든 개장일, 원시 OHLC 100, 거래량 1000, 분할 1, 배당 0.
- 설정: stage "paper", per_order 1000, monthly 5000, buy_fee 0, limit_margin 2, abnormal 10, fractional false, window 15:00–15:45, operating_rule close_at_or_below threshold 200.
- FakeBroker(orderable_cash 500, position 0), FakeNotifier(). now = 2026-11-05 15:30 America/New_York. HALT 파일 없음.

## 요구사항

### REQ-CONFIG-001

설정 파일(TOML)의 숫자 결정값은 필수이며 기본값이 없다. 명령이 쓰는 값이 없거나 형식이 틀리면 그 명령은 주문 없이 종료 코드 2로 끝난다. stage가 없으면 dry-run이다.

### REQ-DATA-001

import-data는 달력·일봉·환율 CSV 스냅샷을 원자적으로 가져오고 SHA-256을 기록한다. 일봉은 원시 OHLC·거래량·분할 계수·주당 배당을 저장한다. 날짜 중복, 거래일 누락, 0 이하 가격, 달력 미포함이 있으면 아무것도 바꾸지 않고 종료 코드 2로 거부한다.

### REQ-STORE-001

저장소는 WAL 모드 SQLite 파일 하나이고 모든 테이블은 STRICT다. (거래일, 규칙)당 주문 1건을 DB UNIQUE 제약으로 보장한다.

### REQ-BT-001

백테스트 시뮬레이션: T일 종가로 판단한 주문을 T+1일 LOC로 체결하거나 미체결로 처리한다. 수량은 지정가 기준으로 주문 시점에 고정하고 소수점 미지원 시 내림하며 남은 현금은 이월한다. 기준선, 종가 X달러 이하 전액 매수 규칙, KRW 환산과 환전 비용, 배당 원천징수, 분할 이벤트, 수수료를 처리하고 규칙별 지표를 계산한다.

### REQ-BT-002

백테스트는 봉을 날짜순으로 하나씩 넘기며 지표를 증분 계산한다. T일까지의 판단은 T+1일 이후 데이터의 영향을 받지 않는다.

### REQ-BT-003

backtest 명령은 조정 구간과 평가 구간을 분리한 규칙별 지표, 시작 월을 바꾼 롤링 창 결과, 채택 판정, 선택 규칙(채택 규칙이 없으면 baseline), 데이터 파일 해시를 JSON으로 출력한다. 잘못된 rules 파일이면 종료 코드 2로 끝난다.

### REQ-BT-004

백테스트 전용 ma_band 실험 규칙: 분할 조정 N일 이동평균보다 일정 비율 이상 오르면 보유 주식 일부를 T+1 종가로 판 것으로 시뮬레이션하고, 이동평균 기준 이하로 내려오면 그 현금을 다시 매수한다. 매도 수수료, 연간 공제 후 양도소득세를 반영하고 매도 횟수, 실현 손익, 세금을 지표에 추가한다. 운영(run)에서는 이 규칙을 쓸 수 없고 증권사 매도 기능도 만들지 않는다.

### REQ-ORDER-001

지정가는 직전 종가 × (1 + 지정가 여유)이다. 주문 금액은 규칙 금액, 주문가능금액, 1회 한도, 월 한도 잔액 중 최솟값이고 수량은 그 금액으로 내림 계산한다.

### REQ-RUN-001

run(paper, 주입된 FakeBroker)은 판단·안전 장치를 통과하면 SENDING을 커밋한 뒤 LOC 매수 1건을 전송한다. 다음 실행에서 체결·미체결을 대조해 반영하고, 같은 거래일에는 재주문하지 않는다. dry-run은 의도만 DRY_RUN으로 기록하고 전송하지 않는다. 1회 한도 적용 시 경고, 월 한도 소진 시 중단, 현금 부족 시 알림을 보낸다.

### REQ-RUN-002

결과를 모르는 SENDING 주문은 재전송하지 않고 증권사 주문 내역으로 연결한다. 찾지 못하면 UNKNOWN으로 두고 알린다. 장 마감 후 내역과 잔고로 확정하기 전에는 새 주문을 내지 않는다.

### REQ-RUN-003

매 실행은 증권사 보유 수량과 DB 보유 수량을 대조한다(분할 반영 포함). 불일치하면 신규 주문을 중단하고 알리며, adjust로 사유를 기록하고 수량이 맞을 때만 재개한다.

### REQ-RUN-004

휴장일, 달력 정보 없음, 주문 시간대 밖, 직전 거래일 봉 없음, 분할 기록 없는 이상 가격, HALT 파일, live 단계, 증권사 어댑터 없음, 시간대 데이터 없음이면 주문 전송 0회로 정해진 사유와 종료 코드를 남긴다.

### REQ-RUN-005

주문 시간대 판단은 America/New_York 기준이다. 서머타임 전환과 무관하게 뉴욕 시각으로 판단하고, 조기 폐장일에는 달력 마감 시각에 맞춰 시간대를 앞당긴다.

### REQ-NOTIFY-001

거래일마다 결과 요약을 1건 보낸다(주문이 없는 날 포함). 안전 장치와 오류는 즉시 보낸다(안전 장치·경고는 날짜·사유당 1회). 알림 실패는 주문 상태와 종료 코드를 바꾸지 않는다.

### REQ-STATUS-001

status는 누적 주수, 평균 단가, 최근 주문, 중단 사유를 JSON으로 출력하고, adjust는 보유 수량 차이와 사유를 기록한다.

### REQ-TEST-001

기본 테스트는 네트워크 없이 FakeBroker와 FakeNotifier로 실행된다.

## 비즈니스 시나리오

### SCN-CONFIG-001 → REQ-CONFIG-001

- Given: 픽스처 F 데이터를 가져온 DB와, limits.per_order_usd만 빠진 설정 파일
- When: main(["--config", 설정, "run"], broker=FakeBroker(500, 0), notifier=FakeNotifier(), now=2026-11-05 15:30 ET)
- Then: 반환값 2, FakeBroker.place_calls == 0, FakeNotifier에 kind "ERROR" 알림 1건 이상

### SCN-CONFIG-002 → REQ-CONFIG-001

- Given: order.limit_margin_pct = "abc"(문자열)인 설정과 유효한 rules 파일
- When: main(["--config", 설정, "backtest", "--rules", rules])
- Then: 반환값 2, stdout이 비어 있음

### SCN-CONFIG-003 → REQ-CONFIG-001

- Given: stage 키가 없는 설정 파일
- When: load_config(경로)
- Then: config.stage == "dry-run"

### SCN-CONFIG-004 → REQ-CONFIG-001

- Given: paths.database만 있고 숫자 결정값이 하나도 없는 설정과 유효한 달력 CSV
- When: main(["--config", 설정, "import-data", "--file", 달력CSV])
- Then: 반환값 0

### SCN-DATA-001 → REQ-DATA-001

- Given: 달력 2026-11-02~2026-11-06 평일 개장(16:00)을 가져온 DB와, 같은 5일의 일봉 CSV(2026-11-04 행: open 99.5, high 101.25, low 98, close 100, volume 1234, split_factor 1, dividend 0.25)
- When: import_csv(store, 일봉CSV)
- Then: ImportResult.kind == "bars", rows == 5, sha256 == 파일 바이트의 SHA-256 16진수. 저장된 2026-11-04 봉의 각 값이 Decimal("99.5"), Decimal("101.25"), Decimal("98"), Decimal("100"), 1234, Decimal("1"), Decimal("0.25")

### SCN-DATA-002 → REQ-DATA-001

- Given: SCN-DATA-001의 일봉을 이미 가져온 DB와, 2026-11-03이 두 번 나오는 새 일봉 CSV
- When: main(["--config", 설정, "import-data", "--file", 새CSV])
- Then: 반환값 2, DB의 일봉은 이전 5건 그대로이고 기록된 해시도 이전 파일 해시 그대로

### SCN-DATA-003 → REQ-DATA-001

- Given: 달력 2026-11-02~11-06 개장, 2026-11-04 행이 빠진 일봉 CSV
- When: import_csv(store, CSV)
- Then: DataImportError 발생, 저장된 일봉 0건

### SCN-DATA-004 → REQ-DATA-001

- Given: 달력 2026-11-02~11-06 개장, 2026-11-05 close가 0인 일봉 CSV와, 별도로 2026-11-05 open이 -1인 일봉 CSV
- When: 각 CSV를 import_csv로 가져온다
- Then: 두 경우 모두 DataImportError, 저장된 일봉 0건

### SCN-DATA-005 → REQ-DATA-001

- Given: 달력이 2026-11-02~11-06만 있고 일봉 CSV가 2026-11-02~2026-11-09
- When: import_csv(store, CSV)
- Then: DataImportError 발생(달력 미포함), 저장된 일봉 0건

### SCN-STORE-001 → REQ-STORE-001

- Given: 새 경로
- When: Store.open(경로)로 DB를 만든 뒤 sqlite3로 PRAGMA journal_mode와 sqlite_master의 table SQL을 조회한다
- Then: journal_mode == "wal", 프로그램이 만든 모든 테이블의 CREATE 문에 STRICT 포함

### SCN-STORE-002 → REQ-STORE-001

- Given: insert_order_intent(2026-11-05, "le200", 4, 102.00, "SENDING")가 이미 성공한 DB
- When: insert_order_intent(2026-11-05, "le200", 2, 102.00, "SENDING")를 다시 호출한다
- Then: DuplicateOrderError 발생, list_orders()에서 2026-11-05/le200 행은 1건이고 quantity 4

### SCN-BT-001 → REQ-BT-001

- Given: 거래일 6개 종가 100,100,50,50,100,100(OHLC 동일, 분할 1, 배당 0), USD 입금 100, every_n_trading_days n=2, 수수료 0, 지정가 여유 0, fractional true
- When: simulate(bars, [], settings)
- Then: baseline decisions가 (1일차, 수량 1, 지정가 100), (3일차, 2, 50), (5일차, 1, 100). metrics[baseline]: final_shares 4, cash_usd 0, equivalent_shares 4, total_deposit_usd 300, average_cost_usd 75, unfilled_count 0, cash_waiting_days 0

### SCN-BT-002 → REQ-BT-001

- Given: SCN-BT-001과 같은 데이터·설정, 규칙 Rule("le60", "close_at_or_below", 60)
- When: simulate(bars, [le60], settings)
- Then: le60 decisions가 (3일차, 수량 4, 지정가 50) 1건뿐이고 4일차에 체결된다. metrics[le60]: final_shares 4, cash_usd 100, equivalent_shares 5, total_deposit_usd 300, average_cost_usd 50, unfilled_count 0, cash_waiting_days 4, final_shares_diff_vs_baseline 0, equivalent_shares_diff_vs_baseline 1

### SCN-BT-003 → REQ-BT-001

- Given: 거래일 4개 종가 모두 100, USD 입금 250, n=2, 수수료 0, 여유 0, fractional false
- When: simulate(bars, [], settings)
- Then: baseline decisions (1일차, 2, 100), (3일차, 3, 100). final_shares 5, cash_usd 0, total_deposit_usd 500

### SCN-BT-004 → REQ-BT-001

- Given: 거래일 2개 종가 100, 101, USD 입금 100, n=10, 수수료 0, 여유 0, fractional true
- When: simulate(bars, [], settings)
- Then: baseline final_shares 0, cash_usd 100, unfilled_count 1, equivalent_shares 100/101을 0.000001 내림한 0.990099

### SCN-BT-005 → REQ-BT-001

- Given: 거래일 2개 종가 100, 100, KRW 입금 130000, n=10, 환율 1일차 1300, 환전 비용 1%, 수수료 0, 여유 0, fractional true
- When: simulate(bars, [], settings, fx_rates)
- Then: baseline total_deposit_usd 99.00, final_shares 0.99, cash_usd 0

### SCN-BT-006 → REQ-BT-001

- Given: 거래일 3개 종가 100,100,100, 3일차 dividend 0.5, USD 입금 400, n=10, 원천징수 15%, 수수료 0, 여유 0, fractional false
- When: simulate(bars, [], settings)
- Then: 2일차에 4주 체결. 3일차 배당 1.70 입금. baseline final_shares 4, cash_usd 1.70, total_deposit_usd 400(배당은 입금액에 포함하지 않음)

### SCN-BT-007 → REQ-BT-001

- Given: 거래일 3개 종가 100, 100, 50이고 3일차 split_factor 2, USD 입금 100, n=10, 수수료 0, 여유 0, fractional true
- When: simulate(bars, [], settings)
- Then: 2일차 1주 체결 후 3일차 보유 2주. baseline final_shares 2, equivalent_shares 2, average_cost_usd 50

### SCN-BT-008 → REQ-BT-001

- Given: 거래일 2개 종가 100, 100, USD 입금 101, n=10, 수수료 1%, 여유 0, fractional false
- When: simulate(bars, [], settings)
- Then: decision 수량 1, 지정가 100. 2일차 체결 대금 100 + 수수료 1.00. final_shares 1, cash_usd 0, average_cost_usd 101

### SCN-BT-009 → REQ-BT-002

- Given: 데이터 A = SCN-BT-001의 6일. 데이터 B = 1~3일차는 A와 같고 4~6일차 종가가 10, 500, 1. 설정은 SCN-BT-001과 같고 규칙 le60
- When: A와 B를 각각 simulate한다
- Then: 판단일이 3일차 이하인 decisions(baseline과 le60 모두)가 A와 B에서 같다

### SCN-BT-010 → REQ-BT-003

- Given: 달력 2024-01-01~2025-12-31 모든 평일 개장(16:00), 같은 기간 평일 일봉 종가 100(파일 해시 H), USD 월 입금 100(cycle monthly, day 1), 수수료 0, 여유 0, fractional true, holdout_years 1, rolling_window_years 1, min_outperformance_pct 0, min_rolling_ratio_pct 50, rules 파일에 le60
- When: main(["--config", 설정, "backtest", "--rules", rules])
- Then: 반환값 0. stdout JSON의 data.bars_sha256 == H, segments.evaluation.start == "2025-01-01", segments.tuning.end == "2024-12-31", rolling.le60.windows == 13, adoption.le60.adopted == false, selected_rule == "baseline". segments.evaluation.rules.baseline에 final_shares, cash_usd, equivalent_shares, total_deposit_usd, average_cost_usd, cash_waiting_days, unfilled_count, final_shares_diff_vs_baseline 키가 있음

### SCN-BT-011 → REQ-BT-003

- Given: 평가 구간 규칙 105주, 기준선 100주, 롤링 쌍 10개 중 7개는 규칙 ≥ 기준선, min_outperformance_pct 3, min_rolling_ratio_pct 60
- When: evaluate_adoption(...)
- Then: adopted True, outperformance_pct 5, rolling_ratio_pct 70

### SCN-BT-012 → REQ-BT-003

- Given: (a) 규칙 102, 기준선 100, 롤링 10개 중 10개 ≥, 기준 3%/60%. (b) 규칙 105, 기준선 100, 롤링 10개 중 5개 ≥, 기준 3%/60%
- When: 각각 evaluate_adoption(...)
- Then: (a) adopted False, outperformance_pct 2. (b) adopted False, rolling_ratio_pct 50

### SCN-BT-013 → REQ-BT-003

- Given: SCN-BT-010의 DB·설정과, type이 "rsi"인 규칙이 들어 있는 rules 파일
- When: main(["--config", 설정, "backtest", "--rules", rules])
- Then: 반환값 2, stdout 비어 있음

### SCN-BT-014 → REQ-BT-004

- Given: make_bars 종가 100,100,100,120,120,90,90, 첫 거래일만 입금 100, 수수료·세금 0, 여유 0, fractional true, Rule band(ma_band, ma_days 3, sell_above 10, sell_fraction 100, rebuy_at_or_below 0)
- When: simulate(bars, [band], settings)
- Then: band 판단은 1일 매수 1주@100, 4일 매도 1주@120, 6일 매수 1.333333주@90. band 최종 1.333333주, sell_count 1, realized_gain_usd 20, tax_usd 0. 기준선 1주, 차이 +0.333333

### SCN-BT-015 → REQ-BT-004

- Given: SCN-BT-014와 같은 데이터에 capital_gains_tax_pct 22. (a) 공제 0 (b) annual_exemption_usd 25 (c) 종가 100,100,100,120,120,90,90,90,90,110,110,90, sell_fraction 50, 공제 15를 2025-12-01 시작(두 매도가 같은 해)과 2025-12-19 시작(해가 바뀜)으로 실행
- When: simulate(...)
- Then: (a) tax_usd 4.40, 재매수 1.284444주, cash_usd 0. (b) tax_usd 0, 1.333333주. (c) 같은 해: 매도 2회, 실현 19.17, 세금 0.92. 해가 바뀜: 매도 2회, 세금 0

### SCN-BT-016 → REQ-BT-004

- Given: 종가 100,100,100,120,120,130,140,150, SCN-BT-014의 band 규칙
- When: simulate(...)
- Then: band 최종 0주, cash_usd 120, 환산 0.8주, 기준선 대비 주수 -1, 환산 주수 -0.2

### SCN-BT-017 → REQ-BT-004

- Given: 종가 100,100,100,120,120,60,60,60, 6번째 봉 2:1 분할, rebuy_at_or_below -5
- When: simulate(...)
- Then: 매도 뒤 매수 판단 없음(분할로 가격이 반이 되어도 재매수 신호가 아님), band cash_usd 120, 기준선 2주

### SCN-BT-018 → REQ-BT-004

- Given: SCN-BT-010의 DB와 rules 파일에 ma_band 규칙(ma_days 20, sell_above 15, fraction 50, rebuy 0). (a) sell_sim 설정 있음 (b) sell_sim 없음 (c) fraction 0, ma_days 1, rebuy ≥ sell_above, sell_above ≤0 중 하나
- When: main(["--config", 설정, "backtest", "--rules", rules])
- Then: (a) 반환값 0, band 지표에 sell_count, realized_gain_usd, tax_usd 키. (b)(c) 반환값 2, stdout 비어 있음

### SCN-BT-019 → REQ-BT-004

- Given: 공통 운영 픽스처 F에서 operating_rule.type = "ma_band"
- When: run_once(now=2026-11-05 15:30 ET)
- Then: 반환값 2, reasons ["CONFIG_ERROR"], place 호출 0, 주문 행 0

### SCN-ORD-001 → REQ-ORDER-001

- Given: prev_close 100, limit_margin_pct 2, rule_amount 500, orderable_cash 500, per_order 1000, monthly_remaining 5000, fee 0, fractional false
- When: compute_order(...)
- Then: limit_price 102.00, quantity 4, reason None

### SCN-ORD-002 → REQ-ORDER-001

- Given: prev_close 100, 여유 2, rule_amount 500, orderable_cash 500, per_order 300, monthly_remaining 5000, fee 0, fractional false
- When: compute_order(...)
- Then: limit_price 102.00, quantity 2, amount 300, binding "PER_ORDER_LIMIT"

### SCN-ORD-003 → REQ-ORDER-001

- Given: prev_close 100, 여유 2, rule_amount 50, orderable_cash 50, per_order 1000, monthly_remaining 5000, fee 0, fractional false
- When: compute_order(...)
- Then: quantity 0, reason "INSUFFICIENT_CASH"

### SCN-RUN-001 → REQ-RUN-001

- Given: 픽스처 F
- When: run_once(config, store, broker, notifier, now=2026-11-05 15:30 ET)
- Then: exit_code 0, orders_sent 1, place_calls 1. 전송 요청은 symbol QQQ, trade_date 2026-11-05, quantity 4, limit_price 102.00. list_orders()[0].status == "SENT"이고 broker_order_id가 비어 있지 않음

### SCN-RUN-002 → REQ-RUN-001

- Given: SCN-RUN-001 이후 FakeBroker.settle_close(2026-11-05, 98)
- When: run_once(..., now=2026-11-05 16:30 ET)
- Then: 주문 상태 FILLED, fill_price 98, fill_cost 392.00, store.holdings() == 4, broker.get_orderable_cash_usd() == 108.00, place_calls 1

### SCN-RUN-003 → REQ-RUN-001

- Given: SCN-RUN-001 이후 FakeBroker.settle_close(2026-11-05, 103)
- When: run_once(..., now=2026-11-05 16:30 ET) 후 run_once(..., now=2026-11-05 15:45 ET 시각으로 다시 설정한 실행)
- Then: 주문 상태 UNFILLED, holdings 0, 두 실행 모두 orders_sent 0, place_calls 1, 두 번째 실행 reasons에 "ALREADY_ORDERED"

### SCN-RUN-004 → REQ-RUN-001

- Given: 픽스처 F
- When: run_once(now=2026-11-05 15:30 ET) 후 run_once(now=2026-11-05 15:45 ET)
- Then: place_calls 1, 두 번째 결과 exit_code 0, orders_sent 0, reasons에 "ALREADY_ORDERED"

### SCN-RUN-005 → REQ-RUN-001

- Given: 픽스처 F에서 stage만 "dry-run"
- When: run_once(now=2026-11-05 15:30 ET)
- Then: exit_code 0, place_calls 0, list_orders()에 status DRY_RUN, quantity 4, limit_price 102.00 행 1건, reasons에 "DRY_RUN_RECORDED"

### SCN-RUN-006 → REQ-RUN-001

- Given: 픽스처 F에서 per_order_usd 300
- When: run_once(now=2026-11-05 15:30 ET)
- Then: exit_code 0, 전송 수량 2, 지정가 102.00, FakeNotifier에 kind WARNING, reason "PER_ORDER_LIMIT_APPLIED" 1건

### SCN-RUN-007 → REQ-RUN-001

- Given: 픽스처 F에서 monthly_usd 400. 2026-11-04 15:30 ET 실행으로 4주 지정가 102.00 주문을 보내고, settle_close(2026-11-04, 100)를 한 뒤 2026-11-04 16:30 ET 실행으로 FILLED 400.00을 반영했다. 그다음 FakeBroker 주문가능금액을 500으로 다시 설정
- When: run_once(now=2026-11-05 15:30 ET)
- Then: exit_code 1, reasons에 "MONTHLY_LIMIT_REACHED", place_calls 총 1, FakeNotifier에 kind SAFETY, reason MONTHLY_LIMIT_REACHED 1건

### SCN-RUN-008 → REQ-RUN-001

- Given: 픽스처 F에서 FakeBroker 주문가능금액 50
- When: run_once(now=2026-11-05 15:30 ET)
- Then: exit_code 0, place_calls 0, 주문 행 0건, reasons에 "INSUFFICIENT_CASH", FakeNotifier에 kind WARNING, reason INSUFFICIENT_CASH 1건

### SCN-REC-001 → REQ-RUN-002

- Given: 픽스처 F에서 FakeBroker.fail_next_place("timeout_after_accept")
- When: run_once(now=15:30 ET) 후 run_once(now=15:45 ET), 날짜는 2026-11-05
- Then: 첫 결과 exit_code 2, 주문 상태 SENDING. 두 번째 결과 후 주문 상태 SENT이고 broker_order_id가 FakeBroker의 접수 주문 id와 같음. place_calls 1

### SCN-REC-002 → REQ-RUN-002

- Given: 픽스처 F에서 FakeBroker.fail_next_place("timeout_before_accept")
- When: 2026-11-05 15:30 ET 실행 후 15:40 ET 실행
- Then: 첫 결과 exit_code 2. 두 번째 결과 exit_code 1, 주문 상태 UNKNOWN, reasons에 "UNRESOLVED_ORDER", place_calls 1, FakeNotifier에 kind SAFETY 알림 1건 이상

### SCN-REC-003 → REQ-RUN-002

- Given: SCN-REC-002 상태(UNKNOWN, 증권사 보유 0 = DB 보유 0)와 2026-11-05 일봉(종가 100) 추가 스냅샷
- When: 2026-11-05 16:30 ET 실행 후 2026-11-06 15:30 ET 실행
- Then: 16:30 실행 후 2026-11-05 주문 상태 NOT_PLACED. 2026-11-06 실행은 exit_code 0, orders_sent 1, place_calls 총 2

### SCN-POS-001 → REQ-RUN-003

- Given: 픽스처 F에 adjust(shares 10, reason "초기 보유")로 DB 보유 10, FakeBroker position 11
- When: run_once(now=2026-11-05 15:30 ET)
- Then: exit_code 1, reasons에 "POSITION_MISMATCH", place_calls 0, FakeNotifier에 kind SAFETY, reason POSITION_MISMATCH 1건

### SCN-POS-002 → REQ-RUN-003

- Given: SCN-POS-001 이후 adjust 없이 FakeBroker.set_position(10)
- When: run_once(now=2026-11-05 15:40 ET)
- Then: exit_code 1, reasons에 "POSITION_MISMATCH", place_calls 0

### SCN-POS-003 → REQ-RUN-003

- Given: SCN-POS-001 이후(증권사 11주) main(["--config", 설정, "adjust", "--shares", "1", "--reason", "수동 매수 반영"])가 0을 반환
- When: run_once(now=2026-11-05 15:40 ET)
- Then: store.holdings() == 11, exit_code 0, orders_sent 1

### SCN-POS-004 → REQ-RUN-003

- Given: 픽스처 F에서 2026-11-04 봉이 close 50, split_factor 2이고 2026-11-03 close 100. adjust로 DB 보유 10, FakeBroker position 20. 주문가능금액 500
- When: run_once(now=2026-11-05 15:30 ET)
- Then: store.holdings() == 20. reasons에 POSITION_MISMATCH와 ABNORMAL_PRICE가 없음. exit_code 0, 전송 지정가 51.00, 수량 9

### SCN-POS-005 → REQ-STATUS-001

- Given: 픽스처 F DB
- When: main(["--config", 설정, "adjust", "--shares", "1", "--reason", ""])
- Then: 반환값 2, store.holdings() == 0

### SCN-GRD-001 → REQ-RUN-004

- Given: 픽스처 F(일봉 2026-11-25까지 확장)
- When: run_once(now=2026-11-26 15:30 ET)
- Then: exit_code 0, place_calls 0, reasons에 "MARKET_CLOSED"

### SCN-GRD-002 → REQ-RUN-004

- Given: 픽스처 F
- When: run_once(now=2027-01-04 15:30 ET)
- Then: exit_code 1, place_calls 0, reasons에 "CALENDAR_MISSING"

### SCN-GRD-003 → REQ-RUN-004

- Given: 픽스처 F에서 일봉이 2026-11-03까지만 있음
- When: run_once(now=2026-11-05 15:30 ET)
- Then: exit_code 1, place_calls 0, reasons에 "STALE_BAR"

### SCN-GRD-004 → REQ-RUN-004

- Given: 픽스처 F에서 2026-11-04 close 80(split_factor 1), 2026-11-03 close 100, abnormal_price_pct 10
- When: run_once(now=2026-11-05 15:30 ET)
- Then: exit_code 1, place_calls 0, reasons에 "ABNORMAL_PRICE"

### SCN-GRD-005 → REQ-RUN-004

- Given: 픽스처 F에서 paths.halt_file 경로에 빈 파일이 있음
- When: run_once(now=2026-11-05 15:30 ET)
- Then: exit_code 1, place_calls 0, reasons에 "HALT_FILE"

### SCN-GRD-006 → REQ-RUN-004

- Given: 픽스처 F에서 stage "live"
- When: run_once(..., broker=FakeBroker(500, 0), now=2026-11-05 15:30 ET)
- Then: exit_code 2, place_calls 0, reasons에 "STAGE_NOT_SUPPORTED"

### SCN-GRD-007 → REQ-RUN-004

- Given: 픽스처 F 설정(stage paper)
- When: main(["--config", 설정, "run"], broker=None, notifier=FakeNotifier(), now=2026-11-05 15:30 ET)
- Then: 반환값 2, DB 주문 행 0건

### SCN-GRD-008 → REQ-RUN-004

- Given: 픽스처 F와, 호출하면 zoneinfo.ZoneInfoNotFoundError를 내는 tz_loader
- When: run_once(..., now=2026-11-05 20:30 UTC aware, tz_loader=그 함수)
- Then: exit_code 2, place_calls 0, reasons에 "TIMEZONE_UNAVAILABLE"

### SCN-GRD-009 → REQ-RUN-004

- Given: 픽스처 F
- When: run_once(now=2026-11-05 14:00 ET)
- Then: exit_code 0, place_calls 0, reasons에 "OUTSIDE_WINDOW"

### SCN-TIME-001 → REQ-RUN-005

- Given: window 15:00–15:45, close_time 16:00
- When: is_in_order_window를 2026-10-31 04:30 Asia/Seoul, 2026-11-03 05:30 Asia/Seoul, 2026-11-03 05:50 Asia/Seoul로 각각 호출
- Then: True, True, False

### SCN-TIME-002 → REQ-RUN-005

- Given: window 15:00–15:45, 2026-11-27 close_time 13:00
- When: is_in_order_window를 2026-11-27 12:30 ET와 2026-11-27 15:30 ET로 각각 호출
- Then: True, False

### SCN-NTF-001 → REQ-NOTIFY-001

- Given: 픽스처 F에서 operating_rule threshold 50(종가 100이라 신호 없음)
- When: 2026-11-05의 15:30, 16:15, 16:30 ET에 run_once를 차례로 실행
- Then: 15:30 결과 reasons에 "NO_SIGNAL", exit_code 0. FakeNotifier에 kind DAILY_SUMMARY, trade_date 2026-11-05 알림이 정확히 1건이고 16:15 실행에서 보냄

### SCN-NTF-002 → REQ-NOTIFY-001

- Given: 픽스처 F에서 FakeNotifier(fail=True), per_order_usd 300(경고 알림 발생)
- When: run_once(now=2026-11-05 15:30 ET)
- Then: 예외 없이 exit_code 0, 주문 상태 SENT, 수량 2, place_calls 1

### SCN-NTF-003 → REQ-NOTIFY-001

- Given: 픽스처 F에서 HALT 파일이 있음
- When: 2026-11-05 15:00, 15:15 ET에 run_once를 두 번 실행
- Then: 첫 실행 직후 FakeNotifier에 kind SAFETY, reason HALT_FILE 1건이 있고, 두 번째 실행 후에도 그 알림은 총 1건

### SCN-STS-001 → REQ-STATUS-001

- Given: SCN-RUN-002 완료 상태
- When: main(["--config", 설정, "status"])
- Then: 반환값 0. stdout JSON shares == "4"(Decimal 비교), average_cost_usd == 98, recent_orders[0]의 status FILLED, quantity 4, limit_price 102.00, active_halts == []

### SCN-STS-002 → REQ-STATUS-001

- Given: SCN-POS-001 완료 상태
- When: main(["--config", 설정, "status"])
- Then: 반환값 0, active_halts에 "POSITION_MISMATCH", last_run.exit_code == 1

### SCN-OFF-001 → REQ-TEST-001

- Given: socket.socket과 socket.create_connection을 호출하면 예외를 내도록 패치한 상태와 픽스처 F
- When: run_once(now=2026-11-05 15:30 ET)를 실행하고 settle_close(2026-11-05, 98) 후 16:30 ET에 다시 실행
- Then: 소켓 예외 없이 첫 결과 exit_code 0, 이후 주문 상태 FILLED
