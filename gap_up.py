import streamlit as st
import yfinance as yf
import FinanceDataReader as fdr
import pandas as pd
import re
import time

# --- 페이지 설정 ---
st.set_page_config(page_title="동시호가 수급 기반 갭상승 스캐너", page_icon="🔥", layout="wide")

# --- 빅데이터 최적화: 마스터 데이터 캐싱 ---
@st.cache_data(ttl=3600)
def load_krx_master():
    try:
        df_krx = fdr.StockListing('KRX')
        return dict(zip(df_krx['Name'], df_krx['Code']))
    except Exception:
        return {}

KRX_MASTER = load_krx_master()

# --- 데이터 정제 및 매핑 함수 ---
def parse_and_map_tickers(input_str, market_type):
    if not input_str.strip():
        return []
    
    tokens = re.split(r'[\s,\n]+', input_str.strip())
    cleaned_items = []
    
    for t in tokens:
        if not t:
            continue
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

# --- 분석 핵심 로직 (수급 불균형 원리 반영) ---
def analyze_stocks(stock_list, market_type, gap_limit, vol_limit):
    captured = []
    progress_text = "동시호가 및 장중 수급 데이터를 분석 중입니다..."
    my_bar = st.progress(0, text=progress_text)
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
            
            if prev_close <= 0:
                continue
                
            # 핵심 지표 계산
            gap_pct = ((today_open - prev_close) / prev_close) * 100
            vol_ratio = today_vol / avg_vol_5d if avg_vol_5d > 0 else 0
            
            # [필터 1] 동시호가 매수세 폭발 (Gap >= 제한치)
            # [필터 2] 수급(거래량) 동반 (Vol >= 제한치)
            # [필터 3] 장중 매수 우위 지속 (시가 사수, 양봉 유지)
            is_gap_valid = gap_pct >= gap_limit
            is_vol_valid = vol_ratio >= vol_limit
            is_buying_sustained = today_current >= today_open
            
            if is_gap_valid and is_vol_valid and is_buying_sustained:
                captured.append({
                    "종목명": name,
                    "종목코드": code,
                    "시가 갭 (%)": gap_pct,
                    "수급 강도(거래량 배수)": vol_ratio,
                    "전일 종가": prev_close,
                    "당일 시가": today_open,
                    "현재가": today_current,
                    "상태": "🔥 매수세 장악"
                })
                
        except Exception:
            pass 
            
        my_bar.progress((i + 1) / total, text=f"수급 분석 중: {name} ({i+1}/{total})")
        time.sleep(0.05) 
        
    my_bar.empty()
    return captured

# --- UI 영역 ---
st.title("🔥 동시호가 수급 불균형 포착 스캐너")
st.markdown("""
**작동 원리:** 장 시작 전(8:40~9:00) 발생한 호재로 인해 **'강력한 시장가 매수세'**가 매도세를 압도하여 시가가 점프한 종목을 포착합니다. 
단순한 갭상승을 넘어, 장중에도 차익실현 매물을 소화하며 **양봉을 사수(현재가 ≥ 시가)**하는 진짜 주도주만 걸러냅니다.
""")
st.divider()

# 사이드바 설정
with st.sidebar:
    st.header("⚙️ 수급 필터 설정")
    market = st.radio("시장 선택:", ("한국 주식", "미국 주식"))
    
    st.divider()
    gap_threshold = st.slider("최소 갭상승률 (%) - 동시호가 강도", 1.0, 15.0, 2.0, 0.5)
    vol_threshold = st.slider("최소 거래량 배수 - 수급의 신뢰도", 1.0, 10.0, 1.5, 0.5)
    st.info("💡 종목명과 코드를 섞어 여러 개 입력해도 자동으로 인식합니다.")

# 메인 입력창
if market == "한국 주식":
    placeholder_text = "예: 삼성전자, SK하이닉스, 005380"
    default_text = "삼성전자, SK하이닉스, 현대차, 기아, 셀트리온, 에코프로, POSCO홀딩스, KB금융, 신한지주, NAVER"
else:
    placeholder_text = "예: AAPL, NVDA, TSLA"
    default_text = "AAPL, NVDA, TSLA, MSFT, AMZN, GOOGL, META, AMD, NFLX, PLTR"

user_input = st.text_area(
    f"✍️ 관심 종목 리스트 입력 (구분자 자유):",
    value=default_text,
    placeholder=placeholder_text,
    height=150
)

# 실행 버튼
if st.button("🔍 수급 분석 스캔 시작", type="primary"):
    stocks_to_scan = parse_and_map_tickers(user_input, market)
    
    if not stocks_to_scan:
        st.warning("⚠️ 분석할 종목을 입력해 주세요.")
    else:
        results = analyze_stocks(stocks_to_scan, market, gap_threshold, vol_threshold)
        
        st.subheader("📊 조건 부합 주도주 리스트")
        if results:
            df_results = pd.DataFrame(results)
            currency_format = "{:,.0f}원" if market == "한국 주식" else "${:,.2f}"
            
            st.dataframe(
                df_results.style.format({
                    "시가 갭 (%)": "{:.2f}%",
                    "수급 강도(거래량 배수)": "{:.2f}배",
                    "전일 종가": currency_format,
                    "당일 시가": currency_format,
                    "현재가": currency_format
                }),
                use_container_width=True,
                hide_index=True
            )
            st.success(f"🎯 강력한 매수세가 확인된 {len(results)}개 종목을 포착했습니다.")
        else:
            st.error("❌ 현재 시장에서 조건을 만족하는 종목이 없습니다 (대부분 음봉 전환 또는 수급 부족).")
