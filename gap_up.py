import streamlit as st
import yfinance as yf
import FinanceDataReader as fdr
import pandas as pd
import re
import time

# --- 1. 페이지 및 기본 설정 ---
st.set_page_config(page_title="글로벌 갭상승 주도주 스캐너", page_icon="🔥", layout="wide")

# --- 2. 빅데이터 최적화: 한국 주식 마스터 데이터 캐싱 ---
# 이 함수는 최초 1회만 실행되어 2,000여 개 한국 종목 데이터를 메모리에 기억합니다.
@st.cache_data(ttl=3600)
def load_krx_master():
    try:
        df_krx = fdr.StockListing('KRX')
        return dict(zip(df_krx['Name'], df_krx['Code']))
    except Exception:
        return {}

KRX_MASTER = load_krx_master()

# --- 3. 입력값 정제 및 시장별 맞춤 매핑 ---
def parse_and_map_tickers(input_str, market_type):
    if not input_str.strip():
        return []
    
    # 쉼표, 공백, 줄바꿈 등을 기준으로 종목 분리
    tokens = re.split(r'[\s,\n]+', input_str.strip())
    cleaned_items = []
    
    for t in tokens:
        if not t:
            continue
        t_upper = t.upper()
        
        if market_type == "한국 주식":
            # 6자리 숫자인 경우 (종목코드)
            if t.isdigit() and len(t) == 6:
                cleaned_items.append({"code": t, "name": t})
            # 한글 이름인 경우 (KRX 데이터에서 자동 검색)
            elif t in KRX_MASTER:
                cleaned_items.append({"code": KRX_MASTER[t], "name": t})
            else:
                cleaned_items.append({"code": t, "name": t})
                
        elif market_type == "미국 주식":
            # 미국 주식은 티커 그대로 사용
            cleaned_items.append({"code": t_upper, "name": t_upper})
            
    # 중복 입력 제거 후 반환
    unique_items = {v['code']: v for v in cleaned_items}.values()
    return list(unique_items)

# --- 4. 수급 불균형 핵심 분석 로직 ---
def analyze_stocks(stock_list, market_type, gap_limit, vol_limit):
    captured = []
    progress_text = f"{market_type} 동시호가 및 장중 수급을 분석 중입니다..."
    my_bar = st.progress(0, text=progress_text)
    total = len(stock_list)
    
    for i, stock in enumerate(stock_list):
        code = stock['code']
        name = stock['name']
        
        try:
            # 시장별 데이터 호출 엔진 분리
            if market_type == "한국 주식":
                df = fdr.DataReader(code, last_bday=15) 
            else:
                ticker = yf.Ticker(code)
                df = ticker.history(period="15d")
                info = ticker.info
                name = info.get('shortName', code)
                
            if df is None or len(df) < 6:
                continue
                
            # 최신 일봉 데이터 추출
            prev_close = df['Close'].iloc[-2]
            today_open = df['Open'].iloc[-1]
            today_current = df['Close'].iloc[-1]
            today_vol = df['Volume'].iloc[-1]
            
            # 최근 5거래일 평균 거래량 계산
            avg_vol_5d = df['Volume'].iloc[-6:-1].mean()
            
            if prev_close <= 0:
                continue
                
            # 지표 계산: 시가 갭 비율 및 거래량 폭발 배수
            gap_pct = ((today_open - prev_close) / prev_close) * 100
            vol_ratio = today_vol / avg_vol_5d if avg_vol_5d > 0 else 0
            
            # 갭상승 주도주 3대 필터링
            is_gap_valid = gap_pct >= gap_limit            # 1. 강력한 시가 점프
            is_vol_valid = vol_ratio >= vol_limit          # 2. 거래량 동반 (세력 개입)
            is_buying_sustained = today_current >= today_open # 3. 양봉 사수 (차익실현 매물 소화)
            
            if is_gap_valid and is_vol_valid and is_buying_sustained:
                captured.append({
                    "종목명": name,
                    "티커/코드": code,
                    "시가 갭 (%)": gap_pct,
                    "수급 강도 (배)": vol_ratio,
                    "전일 종가": prev_close,
                    "당일 시가": today_open,
                    "현재가": today_current,
                    "상태": "🔥 매수세 장악"
                })
                
        except Exception:
            pass # 상장폐지 또는 데이터 오류 종목은 조용히 패스
            
        # 진행률 바 업데이트
        my_bar.progress((i + 1) / total, text=f"분석 중: {name} ({i+1}/{total})")
        time.sleep(0.05) # API 과부하 방지 딜레이
        
    my_bar.empty()
    return captured

# --- 5. 화면 UI 구성 ---
st.title("🔥 글로벌 갭상승 주도주 스캐너")
st.markdown("""
장 시작 전 동시호가의 **'강력한 매수 수급 불균형'**으로 시가가 점프하고, 
장중에도 매도 물량을 소화하며 **양봉을 유지**하는 진짜 주도주만 찾아냅니다.
""")
st.divider()

# 사이드바 (설정 영역)
with st.sidebar:
    st.header("🌍 시장 및 조건 설정")
    # 한국 주식 / 미국 주식 선택 라디오 버튼
    market = st.radio("분석할 시장을 선택하세요:", ("한국 주식", "미국 주식"))
    
    st.divider()
    gap_threshold = st.slider("최소 갭상승률 (%) - 매수 강도", 1.0, 15.0, 2.0, 0.5)
    vol_threshold = st.slider("최소 거래량 배수 - 신뢰도", 1.0, 10.0, 1.5, 0.5)

# 메인 화면 (종목 입력 및 실행 영역)
if market == "한국 주식":
    placeholder_text = "예: 삼성전자, SK하이닉스, 005380 (종목명/코드 자유롭게 입력)"
    default_text = "삼성전자, SK하이닉스, 현대차, 기아, 셀트리온, 에코프로, POSCO홀딩스, KB금융, 신한지주, NAVER"
else:
    placeholder_text = "예: AAPL, NVDA, TSLA"
    default_text = "AAPL, NVDA, TSLA, MSFT, AMZN, GOOGL, META, AMD, NFLX, PLTR"

user_input = st.text_area(
    f"✍️ {market} 관심 종목 리스트 입력:",
    value=default_text,
    placeholder=placeholder_text,
    height=120
)

# 실행 버튼 및 결과 출력
if st.button(f"🔍 {market} 수급 분석 시작", type="primary"):
    stocks_to_scan = parse_and_map_tickers(user_input, market)
    
    if not stocks_to_scan:
        st.warning("⚠️ 분석할 종목을 입력해 주세요.")
    else:
        results = analyze_stocks(stocks_to_scan, market, gap_threshold, vol_threshold)
        
        st.subheader(f"📊 {market} 주도주 포착 결과")
        if results:
            df_results = pd.DataFrame(results)
            
            # 시장별 화폐 단위 포맷팅
            currency_format = "{:,.0f}원" if market == "한국 주식" else "${:,.2f}"
            
            st.dataframe(
                df_results.style.format({
                    "시가 갭 (%)": "{:.2f}%",
                    "수급 강도 (배)": "{:.2f}배",
                    "전일 종가": currency_format,
                    "당일 시가": currency_format,
                    "현재가": currency_format
                }),
                use_container_width=True,
                hide_index=True
            )
            st.success(f"🎯 강력한 수급이 확인된 {len(results)}개 종목을 포착했습니다!")
        else:
            st.error("❌ 현재 시장에서 조건을 만족하는 종목이 없습니다 (수급 부족 또는 음봉 전환).")
