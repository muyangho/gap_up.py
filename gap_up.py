import streamlit as st
import yfinance as yf
import pandas as pd
import re
import time
from datetime import timedelta

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="초단타 분봉 갭상승 스캐너", page_icon="⚡", layout="wide")

# --- 2. 입력값 정제 함수 ---
def parse_tickers(input_str, market_type):
    if not input_str.strip():
        return []
    tokens = re.split(r'[\s,\n]+', input_str.strip())
    cleaned_items = []
    
    for t in tokens:
        if not t: continue
        t = t.upper()
        if market_type == "한국 주식":
            # 한국 종목코드는 야후파이낸스 양식(.KS 코스피 / .KQ 코스닥)으로 변환
            # 여기서는 편의상 입력된 6자리 숫자에 .KS를 붙입니다. (코스닥은 직접 .KQ 입력 필요)
            if t.isdigit() and len(t) == 6:
                cleaned_items.append(f"{t}.KS")
            else:
                cleaned_items.append(t)
        else:
            cleaned_items.append(t)
            
    return list(set(cleaned_items))

# --- 3. 실시간 5분봉 분석 로직 ---
def analyze_intraday_momentum(tickers, gap_limit, vol_limit):
    captured = []
    my_bar = st.progress(0, text="실시간 5분봉 데이터 스캔 중...")
    total = len(tickers)
    
    for i, ticker in enumerate(tickers):
        try:
            # 5일 치의 5분봉 데이터를 가져옵니다. (장중 실시간 변동 포착 가능)
            stock = yf.Ticker(ticker)
            df = stock.history(period="5d", interval="5m")
            
            if df.empty or len(df) < 10:
                continue
                
            # 가장 최근 5분봉 데이터 (현재)
            current_bar = df.iloc[-1]
            current_open = current_bar['Open']
            current_price = current_bar['Close']
            current_vol = current_bar['Volume']
            
            # 전일 종가 구하기 (날짜가 바뀌는 시점을 찾아야 함)
            # 5분봉 데이터에서 날짜(date)만 추출하여 그룹화
            df['date'] = df.index.date
            unique_dates = df['date'].unique()
            
            if len(unique_dates) < 2:
                continue
                
            # 어제(또는 직전 거래일)의 마지막 종가
            prev_day_data = df[df['date'] == unique_dates[-2]]
            prev_close = prev_day_data.iloc[-1]['Close']
            
            # 오늘(또는 최근 거래일)의 첫 시가
            today_data = df[df['date'] == unique_dates[-1]]
            today_first_open = today_data.iloc[0]['Open']
            
            # 최근 50개의 5분봉 평균 거래량 (평소 거래량 대비 얼마나 터졌나 확인)
            avg_vol_5m = df['Volume'].iloc[-51:-1].mean()
            
            if prev_close <= 0 or avg_vol_5m <= 0:
                continue
                
            # 지표 계산
            # 1. 갭상승률 (오늘 첫 시가 vs 어제 종가)
            gap_pct = ((today_first_open - prev_close) / prev_close) * 100
            
            # 2. 현재 5분봉의 거래량 폭발 배수
            vol_ratio = current_vol / avg_vol_5m
            
            # 3. 양봉 유지 (현재 가격이 오늘 시가보다 높은가?)
            is_bullish = current_price >= today_first_open
            
            # 조건 필터링
            if (gap_pct >= gap_limit) and (vol_ratio >= vol_limit) and is_bullish:
                info = stock.info
                name = info.get('shortName', ticker)
                
                captured.append({
                    "종목명": name.replace(".KS", ""),
                    "시가 갭 (%)": gap_pct,
                    "5분봉 거래량 폭발 (배)": vol_ratio,
                    "전일 종가": prev_close,
                    "당일 첫 시가": today_first_open,
                    "현재가": current_price,
                    "상태": "⚡ 실시간 수급 폭발"
                })
        except Exception as e:
            pass
            
        my_bar.progress((i + 1) / total, text=f"분석 중: {ticker} ({i+1}/{total})")
        time.sleep(0.1) # 야후 API 차단 방지
        
    my_bar.empty()
    return captured

# --- 4. UI 구성 ---
st.title("⚡ 실시간 5분봉 갭상승 스캐너")
st.markdown("""
이 스캐너는 하루 치가 끝난 일봉이 아닌, **'5분 단위(5m Interval)' 실시간 차트**를 분석합니다. 
장 시작 직후(오전 9시~9시 30분)에 돌리시면, 갭이 뜨고 거래량이 쏟아지며 치고 올라가는 종목을 즉시 잡아냅니다.
""")
st.divider()

with st.sidebar:
    st.header("⚙️ 실시간 초단타 조건")
    market = st.radio("시장 선택:", ("한국 주식", "미국 주식"))
    st.divider()
    gap_threshold = st.slider("최소 시가 갭 (%)", 0.5, 10.0, 1.5, 0.1)
    vol_threshold = st.slider("최소 거래량 폭발 (평소 5분봉 대비 N배)", 1.0, 20.0, 3.0, 0.5)
    st.caption("주의: 장중 실시간 포착이므로 거래량 배수를 3배 이상 높게 잡는 것이 좋습니다.")

if market == "한국 주식":
    placeholder = "예: 005930, 000660 (한국은 코드 6자리만 입력)"
    default_tickers = "005930, 000660, 005380, 000270, 035420, 035720, 068270"
else:
    placeholder = "예: AAPL, NVDA, TSLA"
    default_tickers = "AAPL, NVDA, TSLA, MSFT, AMZN, GOOGL, META, PLTR"

user_input = st.text_area(f"✍️ {market} 감시 종목 입력:", value=default_tickers, placeholder=placeholder, height=100)

if st.button("🚀 실시간 5분봉 스캔 시작", type="primary"):
    stocks_to_scan = parse_tickers(user_input, market)
    
    if not stocks_to_scan:
        st.warning("분석할 종목 코드를 입력해 주세요.")
    else:
        results = analyze_intraday_momentum(stocks_to_scan, gap_threshold, vol_threshold)
        
        st.subheader("📊 실시간 포착 결과")
        if results:
            df_results = pd.DataFrame(results)
            fmt = "{:,.0f}원" if market == "한국 주식" else "${:,.2f}"
            
            st.dataframe(
                df_results.style.format({
                    "시가 갭 (%)": "{:.2f}%",
                    "5분봉 거래량 폭발 (배)": "{:.2f}배",
                    "전일 종가": fmt, "당일 첫 시가": fmt, "현재가": fmt
                }),
                use_container_width=True, hide_index=True
            )
            st.success(f"🎯 실시간으로 수급이 터지고 있는 {len(results)}개 종목을 잡았습니다!")
        else:
            st.error("❌ 현재 시점(5분봉 기준)에서 수급이 폭발하며 갭을 유지 중인 종목이 없습니다.")
            st.info("💡 팁: 이 스캐너는 장 개장 직후(9:00~9:30)에 돌려야 가장 강력한 효과를 발휘합니다.")
