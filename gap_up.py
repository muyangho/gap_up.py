import streamlit as st
import yfinance as yf
import FinanceDataReader as fdr
import pandas as pd
import re
import time

# --- 1. 페이지 및 기본 설정 ---
st.set_page_config(page_title="자동 갭상승 주도주 포착기", page_icon="🤖", layout="wide")

# --- 2. 빅데이터 최적화: 마스터 데이터 및 자동스캔 유니버스 캐싱 ---
@st.cache_data(ttl=3600)
def load_market_data():
    krx_master = {}
    top_krx_codes = []
    
    try:
        # 한국거래소 전체 데이터 로드
        df_krx = fdr.StockListing('KRX')
        krx_master = dict(zip(df_krx['Name'], df_krx['Code']))
        
        # 시가총액 기준 상위 150개 종목을 '자동 스캔' 대상으로 추출
        df_krx_sorted = df_krx.sort_values(by='Marcap', ascending=False).head(150)
        for _, row in df_krx_sorted.iterrows():
            top_krx_codes.append({"code": row['Code'], "name": row['Name']})
    except Exception:
        pass

    # 미국 시총/거래량 상위 100개 주요 티커 하드코딩 (API 과부하 방지)
    top_us_tickers = [
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK-B", "LLY", "V", 
        "JPM", "UNH", "AVGO", "MA", "PG", "JNJ", "HD", "MRK", "COST", "ABBV", 
        "CRM", "BAC", "AMD", "NFLX", "ADBE", "QCOM", "WMT", "KO", "PEP", "TMO", 
        "LIN", "DIS", "MCD", "ACN", "ABT", "INTU", "WFC", "CSCO", "TXN", "AMGN",
        "IBM", "COP", "CMCSA", "CAT", "PFE", "BA", "NOW", "GE", "SPGI", "AMAT",
        "UNP", "HON", "NKE", "GS", "SYK", "LOW", "ELEV", "INTC", "RTX", "BLK",
        "ELV", "LMT", "MDT", "VRTX", "BKNG", "TJX", "C", "REGN", "MMC", "ADP",
        "PGR", "CB", "SLB", "CI", "BDX", "SYY", "BSX", "EOG", "SO", "CME",
        "KLAC", "MU", "PANW", "FI", "SCHW", "ZTS", "ETN", "CSX", "EQIX", "SHW",
        "PLTR", "ARM", "SMCI", "COIN", "CRWD", "UBER", "ABNB", "SNOW", "HOOD", "RIVN"
    ]
    top_us_codes = [{"code": t, "name": t} for t in top_us_tickers]
    
    return krx_master, top_krx_codes, top_us_codes

KRX_MASTER, AUTO_KR_UNIVERSE, AUTO_US_UNIVERSE = load_market_data()

# --- 3. 수동 입력값 정제 함수 ---
def parse_and_map_tickers(input_str, market_type):
    if not input_str.strip():
        return []
    
    tokens = re.split(r'[\s,\n]+', input_str.strip())
    cleaned_items = []
    
    for t in tokens:
        if not t: continue
        t_upper = t.upper()
        
        if market_type == "한국 주식":
            if t.isdigit() and len(t) == 6:
                cleaned_items.append({"code": t, "name": t})
            elif t in KRX_MASTER:
                cleaned_items.append({"code": KRX_MASTER[t], "name": t})
            else:
                cleaned_items.append({"code": t, "name": t})
        elif market_type == "미국 주식":
            cleaned_items.append({"code": t_upper, "name": t_upper})
            
    unique_items = {v['code']: v for v in cleaned_items}.values()
    return list(unique_items)

# --- 4. 수급 불균형 핵심 분석 로직 ---
def analyze_stocks(stock_list, market_type, gap_limit, vol_limit):
    captured = []
    my_bar = st.progress(0, text="데이터 스캔 준비 중...")
    total = len(stock_list)
    
    for i, stock in enumerate(stock_list):
        code = stock['code']
        name = stock['name']
        
        try:
            if market_type == "한국 주식":
                df = fdr.DataReader(code, last_bday=15) 
            else:
                ticker = yf.Ticker(code)
                df = ticker.history(period="15d")
                info = ticker.info
                name = info.get('shortName', code)
                
            if df is None or len(df) < 6:
                continue
                
            prev_close = df['Close'].iloc[-2]
            today_open = df['Open'].iloc[-1]
            today_current = df['Close'].iloc[-1]
            today_vol = df['Volume'].iloc[-1]
            
            avg_vol_5d = df['Volume'].iloc[-6:-1].mean()
            
            if prev_close <= 0: continue
                
            gap_pct = ((today_open - prev_close) / prev_close) * 100
            vol_ratio = today_vol / avg_vol_5d if avg_vol_5d > 0 else 0
            
            is_gap_valid = gap_pct >= gap_limit
            is_vol_valid = vol_ratio >= vol_limit
            is_buying_sustained = today_current >= today_open
            
            if is_gap_valid and is_vol_valid and is_buying_sustained:
                captured.append({
                    "종목명": name,
                    "티커/코드": code,
                    "시가 갭 (%)": gap_pct,
                    "수급 강도 (배)": vol_ratio,
                    "전일 종가": prev_close,
                    "당일 시가": today_open,
                    "현재가": today_current,
                    "상태": "🔥 주도주 포착"
                })
                
        except Exception:
            pass 
            
        # UI 업데이트 (초당 호출 수 제한을 위해 미세 딜레이 적용)
        my_bar.progress((i + 1) / total, text=f"🔍 시장 스캔 중... ({i+1}/{total}) : {name}")
        time.sleep(0.02)
        
    my_bar.empty()
    return captured

# --- 5. 화면 UI 구성 ---
st.title("🤖 퀀트 AI 갭상승 주도주 스캐너")
st.markdown("""
입력할 필요 없이 스캐너가 **시가총액/거래대금 상위 핵심 종목**들을 통째로 뒤져서 조건에 맞는 놈만 발라냅니다.
""")
st.divider()

# 사이드바: 공통 조건 설정
with st.sidebar:
    st.header("⚙️ 스캔 조건 설정")
    gap_threshold = st.slider("최소 갭상승률 (%) - 매수 강도", 1.0, 15.0, 2.0, 0.5)
    vol_threshold = st.slider("최소 거래량 배수 - 신뢰도", 1.0, 10.0, 1.5, 0.5)
    st.info("조건이 너무 빡빡해서 포착이 안 된다면 위 슬라이더를 왼쪽으로 조금 낮춰보세요.")

# 메인 화면: 탭으로 모드 분리
tab1, tab2 = st.tabs(["🤖 시장 주도주 자동 스캔", "✍️ 내 관심종목 수동 스캔"])

# [탭 1] 자동 스캔 모드
with tab1:
    st.subheader("시장 전체 핵심 종목 자동 분석")
    st.write("알아서 우량주 풀(한국 150개, 미국 100개)을 뒤져 갭상승 종목을 포착합니다.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🇰🇷 한국 주식 자동 스캔 (Top 150)", use_container_width=True):
            market = "한국 주식"
            st.write("한국 시장 시가총액 상위 150개 종목을 스캔합니다...")
            results = analyze_stocks(AUTO_KR_UNIVERSE, market, gap_threshold, vol_threshold)
            st.session_state['auto_results'] = (results, market)

    with col2:
        if st.button("🇺🇸 미국 주식 자동 스캔 (Top 100)", use_container_width=True):
            market = "미국 주식"
            st.write("미국 시장 주요 테크 및 시총 상위 100개 종목을 스캔합니다...")
            results = analyze_stocks(AUTO_US_UNIVERSE, market, gap_threshold, vol_threshold)
            st.session_state['auto_results'] = (results, market)

    # 자동 스캔 결과 출력
    if 'auto_results' in st.session_state:
        res, mkt = st.session_state['auto_results']
        if res:
            df_res = pd.DataFrame(res)
            currency_fmt = "{:,.0f}원" if mkt == "한국 주식" else "${:,.2f}"
            st.dataframe(
                df_res.style.format({
                    "시가 갭 (%)": "{:.2f}%",
                    "수급 강도 (배)": "{:.2f}배",
                    "전일 종가": currency_fmt, "당일 시가": currency_fmt, "현재가": currency_fmt
                }), use_container_width=True, hide_index=True
            )
            st.success(f"🎯 깐깐한 조건을 통과한 {len(res)}개의 주도주를 찾아냈습니다!")
        else:
            st.error("❌ 현재 시장에서는 설정한 수급 조건을 완벽히 만족하는 주도주가 없습니다. (조건을 낮춰보세요)")

# [탭 2] 수동 스캔 모드 (기존 기능 유지)
with tab2:
    st.subheader("내가 고른 관심종목 집중 분석")
    market_manual = st.radio("시장 선택:", ("한국 주식", "미국 주식"), horizontal=True)
    
    user_input = st.text_area(
        "종목명 또는 코드 입력 (띄어쓰기로 구분):", 
        placeholder="예: 삼성전자 카카오 SK하이닉스 005380 (또는 AAPL TSLA NVDA)",
        height=100
    )
    
    if st.button("🔍 내 관심종목 스캔", type="primary"):
        stocks_to_scan = parse_and_map_tickers(user_input, market_manual)
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
                        "수급 강도 (배)": "{:.2f}배",
                        "전일 종가": currency_fmt, "당일 시가": currency_fmt, "현재가": currency_fmt
                    }), use_container_width=True, hide_index=True
                )
            else:
                st.error("❌ 관심종목 중에는 현재 조건을 만족하는 주식이 없습니다.")
