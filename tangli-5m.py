import ccxt, pandas as pd, datetime, time, concurrent.futures, requests

# ==========================================
# 🔥 核心策略参数 (5分钟超短线版)
# ==========================================
TIMEFRAME = '5m'           # 🔴 修改：改为5分钟级别
SQUEEZE_THRESHOLD = 0.025  # 🔴 修改：压缩阈值降为 2.5%。5m级别波动小，超过3%通常已经是大波动了
MAX_FUNDING_RATE = 0.0005  # 🔴 修改：短线稍微放宽费率限制
RISK_REWARD_RATIO = 1.5    # 盈亏比保持 1.5 (激进者可改为 1.2 提高胜率)
VOL_MULTIPLIER = 2.0       # 🔴 新增：成交量放大倍数。5m假突破多，建议要求2倍放量才进场

# WxPusher 配置
APP_TOKEN = 'AT_PJpFzWEEcp7r4HEKV6KhYKWBYyGQrZcp'
UIDS = [
    'UID_YxgkBxsTEeQ2gEZaZKcOn1kbNyPl', 
    'UID_13uYApHARP47TeWfTgJCgKJwy0W9',
    'UID_2GGbSwMDZFFBBkj4HKTauQAv8oJz'
    'UID_IDzkhzteowCRWTM7TfmDZvtODwJZ'
    'UID_SL7WeaH8fCIYzTTNDTk9EpAMy8oD'
    'UID_cEnTZVBsOm1FiSnpnPdK2xJopDdh'
]

# 初始化 OKX
exchange = ccxt.okx({'timeout': 15000, 'enableRateLimit': True, 'options': {'defaultType': 'swap'}})

def analyze_logic(symbol, rate):
    try:
        # 获取 K 线数据
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=100)
        if len(ohlcv) < 65: return None
        df = pd.DataFrame(ohlcv, columns=['ts','o','h','l','c','v'])
        
        # 指标计算
        df['ma20'] = df['c'].rolling(20).mean()
        df['std'] = df['c'].rolling(20).std()
        # 布林带宽度计算
        df['bw'] = (df['ma20'] + 2*df['std'] - (df['ma20'] - 2*df['std'])) / df['ma20']
        # ATR 计算 (14周期)
        df['atr'] = pd.concat([df['h']-df['l'], (df['h']-df['c'].shift(1)).abs()], axis=1).max(axis=1).rolling(14).mean()
        
        t, d1 = df.iloc[-1], df.iloc[-2]
        price, atr = t['c'], t['atr']

        # 🚀 5分钟级别过滤逻辑
        # 必须是“之前窄幅震荡(d1['bw']小)，当前突然放量(t['v']大)突破”
        
        # 1. 之前处于静默期 (布林带压缩)
        if d1['bw'] < SQUEEZE_THRESHOLD:
            # 2. 当前必须剧烈放量 (过滤掉无量假突破)
            if t['v'] > df['v'].tail(10).mean() * VOL_MULTIPLIER: # 对比过去10根K线的平均成交量
                
                # 🟢 做多条件
                if t['c'] > d1['ma20'] + 2*d1['std'] and rate < MAX_FUNDING_RATE:
                    return {
                        '币种': symbol.split(':')[0], '指令': '🚀 5m 爆发做多', 
                        '价格': price, '止损': round(price - atr*2, 5), '止盈': round(price + atr*2*RISK_REWARD_RATIO, 5)
                    }
                
                # 🔴 做空条件
                if t['c'] < d1['ma20'] - 2*d1['std'] and rate > -MAX_FUNDING_RATE:
                    return {
                        '币种': symbol.split(':')[0], '指令': '📉 5m 破位做空', 
                        '价格': price, '止损': round(price + atr*2, 5), '止盈': round(price - atr*2*RISK_REWARD_RATIO, 5)
                    }
    except: return None

if __name__ == '__main__':
    start = time.time()
    print(f"🌍 正在扫描 OKX {TIMEFRAME} 级别数据...")
    
    try:
        rates = {s: data['fundingRate'] for s, data in exchange.fetch_funding_rates().items()}
        # 🔴 优化：只扫描成交量前 100 的币种，防止小币种5m画门
        all_symbols = [s for s in exchange.load_markets() if ':USDT' in s and exchange.markets[s]['active']]
        # 简单粗暴全部扫描，如果太慢可以考虑加过滤逻辑
        symbols = all_symbols 
    except Exception as e:
        print(f"❌ 初始化失败: {e}"); exit()
    
    results = []
    # 5分钟级别对速度要求高，线程数开到 50 (注意不要超过API限制)
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as exe:
        futures = {exe.submit(analyze_logic, s, rates.get(s, 0)): s for s in symbols}
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res: results.append(res)
            
    # 推送逻辑
    beijing_tz = datetime.timezone(datetime.timedelta(hours=8))
    timestamp = datetime.datetime.now(beijing_tz).strftime('%m-%d %H:%M')
    url = 'http://wxpusher.zjiecode.com/api/send/message'
    
    if results:
        content = f"<h1>⚡ 金芈智选 ({timestamp})</h1>"
        # 按价格排序没意义，不如按币种名排序
        for s in sorted(results, key=lambda x: x['币种']):
            content += f"<h2>{s['指令']}：{s['币种']}</h2>📍 现价：{s['价格']}<br/>🛡️ 止损：{s['止损']}<br/>🎯 止盈：{s['止盈']}<br/>------------------<br/>"
        summary = f"⚡ 5m级别发现 {len(results)} 个急变盘！"
    else:
        content = f"<h3>☕ 5m 市场平静 ({timestamp})</h3><p>全市场 {len(symbols)} 币种扫描完毕。暂无满足“极致压缩+2倍放量”的标的。</p>"
        summary = "☕ 5m 暂无机会"

    for uid in UIDS:
        try:
            requests.post(url, json={
                "appToken": APP_TOKEN, "content": content, "uids": [uid], "contentType": 2, "summary": summary
            })
        except Exception as e:
            print(f"推送失败: {e}")
    
    print(f"🏁 扫描耗时: {int(time.time() - start)} 秒")
