import streamlit as st
import yfinance as yf
import FinanceDataReader as fdr
import pandas as pd
import re
import time

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="All-Time 갭상승 자동 스캐너", page_icon="🌌", layout="wide")

# --- 2. 빅데이터 캐싱: 한국/미국 주도주 유니버스 자동 장착 ---
@st.cache_data(ttl=3600)
def load_auto_universe():
    krx_master = {}
    top_krx_codes = []
    
    try:
        # 한국: 전체 종목을 불러온 뒤 시가총액(Marcap) 기준 상위 150개 자동 추출
        df_krx = fdr.StockListing('KRX')
        krx_master = dict(zip(df_krx['Name'], df_krx['Code']))
        
        df_krx_sorted = df_krx.sort_values(by='Marcap', ascending=False).head(150)
        for _, row in df_krx_sorted.iterrows():
            top_krx_codes.append({"code": row['Code'], "name": row['Name']})
    except Exception:
        pass

    # 미국: 시장을 주도하는 메가테크 및 섹터 대장주 100개 (API 과부하 방지용 하드코딩)
    top_us_tickers = [
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK-B", "LLY", "V", 
        "JPM", "UNH", "AVGO", "MA", "PG", "JNJ", "HD", "MRK", "COST", "ABBV", 
        "CRM", "BAC", "AMD", "NFLX", "ADBE", "QCOM", "WMT", "KO", "PEP", "TMO", 
        "LIN", "DIS", "MCD", "ACN", "ABT", "INTU", "WFC", "CSCO", "TXN", "AMGN",
        "IBM", "COP", "CMCSA", "CAT", "PFE", "BA", "NOW", "GE", "SPGI", "AMAT",
        "UNP", "HON", "NKE", "GS", "SYK", "LOW", "ELEV", "INTC", "RTX", "BLK",
        "LMT", "MDT", "VRTX", "BKNG", "TJX", "C", "REGN", "MMC", "ADP",
        "PGR", "CB", "SLB", "CI", "BDX", "SYY", "BSX", "EOG", "SO", "CME",
        "KLAC", "MU", "PANW", "FI", "SCHW", "ZTS", "ETN", "CSX", "EQIX", "SHW",
        "PLTR", "ARM", "SMCI", "COIN", "CRWD", "UBER", "ABNB", "SNOW", "HOOD", "RIVN"
    ]
    top_us_codes = [{"code": t, "name": t} for t in top_us_tickers]
    
    return krx_master, top_krx_codes, top_us_codes

KRX_MASTER, AUTO_KR_UNIVERSE, AUTO_US_UNIVERSE = load_auto_universe()

# --- 3. 수동 입력값 정제 함수 ---
def parse_manual_input(input_str, market_type):
    if not input_str.strip(): return []
    tokens = re.split(r'[\s,\n]+', input_str.strip())
    cleaned_items = []
    for t in tokens:
        if not t: continue
        t_up = t.upper()
        if market_type == "한국 주식":
            if t.isdigit() and len(t) == 6:
                cleaned_items.append({"code": t, "name": t})
            elif t in KRX_MASTER:
                cleaned_items.append({"code": KRX_MASTER[t], "name": t})
            else:
                cleaned_items.append({"code": t, "name": t})
        else:
            cleaned_items.append({"code": t_up, "name": t_up})
    return list({v['code']: v for v in cleaned_items}.values())

# --- 4. 전천후(All-Time) 핵심 분석 로직 ---
def analyze_stocks(stock_list, market_type, gap_limit, vol_limit):
    captured = []
    my_bar = st.progress(0, text="데이터 스캔 준비 중...")
    total = len(stock_list)
    
    for i, stock in enumerate(stock_list):
        code = stock['code']
        name = stock['name']
        
        try:
            # 장중, 장후 상관없이 가장 최신의 15일치 일봉(Daily) 데이터를 가져옴
            if market_type == "한국 주식":
                df = fdr.DataReader(code, last_bday=15) 
            else:
                ticker = yf.Ticker(code)
                df = ticker.history(period="15d")
                info = ticker.info
                name = info.get('shortName', code)
                
            if df is None or len(df) < 6:
                continue
                
            # 최신 2거래일 데이터 추출 (오늘이 장중이면 오늘 실시간, 장마감이면 오늘 최종, 주말이면 금요일 기준)
            prev_close = df['Close'].iloc[-2]
            today_open = df['Open'].iloc[-1]
            today_current = df['Close'].iloc[-1]
            today_vol = df['Volume'].iloc[-1]
            
            avg_vol_5d = df['Volume'].iloc[-6:-1].mean()
            
            if prev_close <= 0: continue
                
            # 지표 계산
            gap_pct = ((today_open - prev_close) / prev_close) * 100
            vol_ratio = today_vol / avg_vol_5d if avg_vol_5d > 0 else 0
            
            # 조건 필터링
            is_gap_valid = gap_pct >= gap_limit
            is_vol_valid = vol_ratio >= vol_limit
            is_buying_sustained = today_current >= today_open # 양봉(시가 방어) 확인
            
            if is_gap_valid and is_vol_valid and is_buying_sustained:
                captured.append({
                    "종목명": name,
                    "코드/티커": code,
                    "시가 갭 (%)": gap_pct,
                    "수급(거래량)": vol_ratio,
                    "전일 종가": prev_close,
                    "당일 시가": today_open,
                    "현재가(종가)": today_current,
                    "상태": "✅ 모멘텀 확인"
                })
                
        except Exception:
            pass 
            
        # UI 업데이트 방어코드 (API 과부하 및 에러 방지)
        my_bar.progress((i + 1) / total, text=f"🔍 시장 스캔 중... ({i+1}/{total}) : {name}")
        time.sleep(0.02)
        
    my_bar.empty()
    return captured

# --- 5. UI 화면 구성 ---
st.title("🌌 All-Time 갭상승 주도주 스캐너")
st.markdown("""
입력할 필요가 없습니다. 
시간에 상관없이, 버튼 한 번만 누르면 **한국 시가총액 Top 150**과 **미국 메가테크 Top 100**을 자동으로 스캔하여 오늘(또는 최근 거래일) 갭상승 모멘텀이 터진 종목을 발라냅니다.
""")
st.divider()

# 사이드바
with st.sidebar:
    st.header("⚙️ 스캔 조건")
    # 포착이 안되는 답답함을 방지하기 위해 기본값을 현실적으로 세팅
    gap_threshold = st.slider("최소 갭상승 (%)", 0.5, 10.0, 1.0, 0.5)
    vol_threshold = st.slider("최소 거래량 폭발 (배수)", 0.5, 5.0, 0.8, 0.1)
    st.info("장 초반(9시~10시)에 스캔할 때는 아직 그날 거래량이 다 안 찼으므로, '최소 거래량 배수'를 0.5배 이하로 낮추고 돌리는 것이 팁입니다.")

# 탭 메뉴
tab1, tab2 = st.tabs(["🤖 시장 자동 스캔 (추천)", "✍️ 수동 입력 스캔"])

# [탭 1] 자동 스캔 모드
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🇰🇷 한국 주식 자동 스캔 (Top 150)", use_container_width=True, type="primary"):
            market = "한국 주식"
            results = analyze_stocks(AUTO_KR_UNIVERSE, market, gap_threshold, vol_threshold)
            st.session_state['auto_results'] = (results, market)

    with col2:
        if st.button("🇺🇸 미국 주식 자동 스캔 (Top 100)", use_container_width=True, type="primary"):
            market = "미국 주식"
            results = analyze_stocks(AUTO_US_UNIVERSE, market, gap_threshold, vol_threshold)
            st.session_state['auto_results'] = (results, market)

    # 결과 테이블 렌더링
    if 'auto_results' in st.session_state:
        res, mkt = st.session_state['auto_results']
        if res:
            df_res = pd.DataFrame(res)
            currency_fmt = "{:,.0f}원" if mkt == "한국 주식" else "${:,.2f}"
            st.dataframe(
                df_res.style.format({
                    "시가 갭 (%)": "{:.2f}%",
                    "수급(거래량)": "{:.2f}배",
                    "전일 종가": currency_fmt, "당일 시가": currency_fmt, "현재가(종가)": currency_fmt
                }), use_container_width=True, hide_index=True
            )
            st.success(f"🎯 총 {len(res)}개의 조건 부합 종목을 포착했습니다!")
        else:
            st.error("❌ 현재 시장(또는 최근 거래일) 기준 조건을 만족하는 종목이 없습니다. 슬라이더 조건을 더 낮춰보세요.")

# [탭 2] 수동 스캔 모드
with tab2:
    market_manual = st.radio("분석 시장:", ("한국 주식", "미국 주식"), horizontal=True)
    user_input = st.text_area(
        "종목명 또는 코드 입력 (띄어쓰기/콤마 구분):", 
        placeholder="예: 카카오, 에코프로, 005930 (또는 AAPL, TSLA, NVDA)"
    )
    
    if st.button("🔍 입력 종목 스캔", type="secondary"):
        stocks_to_scan = parse_manual_input(user_input, market_manual)
        if not stocks_to_scan:
            st.warning("분석할 종목을 창에 입력해 주세요.")
        else:
            res_manual = analyze_stocks(stocks_to_scan, market_manual, gap_threshold, vol_threshold)
            if res_manual:
                df_man = pd.DataFrame(res_manual)
                currency_fmt = "{:,.0f}원" if market_manual == "한국 주식" else "${:,.2f}"
                st.dataframe(
                    df_man.style.format({
                        "시가 갭 (%)": "{:.2f}%",
                        "수급(거래량)": "{:.2f}배",
                        "전일 종가": currency_fmt, "당일 시가": currency_fmt, "현재가(종가)": currency_fmt
                    }), use_container_width=True, hide_index=True
                )
            else:
                st.error("❌ 입력하신 종목 중에는 조건을 만족하는 주식이 없습니다.")
