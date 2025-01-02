import time
import pandas as pd
import numpy as np
import requests
import websocket
import json
import logging
from datetime import datetime
import threading
from queue import Queue
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from websocket import WebSocketConnectionClosedException
import ssl
import socket

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('price_monitor.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# API配置
REST_URL = "https://fapi.binance.com"
WS_URL = "wss://fstream.binance.com/ws"
WS_KLINE_URL = "wss://fstream.binance.com/ws"  # WebSocket K线订阅
KLINE_URL = REST_URL + "/fapi/v1/klines"
EXCHANGE_INFO_URL = REST_URL + "/fapi/v1/exchangeInfo"

# 飞书机器人配置
FEISHU_WEBHOOK = 'https://www.feishu.cn/flow/api/trigger-webhook/2fb4a9b848c591d77bcf57bfcee1b37a'

# 全局变量
price_queue = Queue()
position_records = {}  # 记录每个币种的位置
last_alert_times = {}  # 记录每个币种的最后警报时间
alert_cooldown = 3600  # 警报冷却时（秒）
kline_data = {}  # 存储每个币种的K线数据

# 配置请求会话
session = requests.Session()
retry_strategy = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)
adapter = HTTPAdapter(max_retries=retry_strategy, pool_maxsize=100)
session.mount("http://", adapter)
session.mount("https://", adapter)

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_initial_data(symbol, max_retries=5):
    """获取初始K线数据，添加重试机制"""
    for attempt in range(max_retries):
        try:
            params = {
                'symbol': symbol,
                'interval': '1h',
                'limit': 300
            }
            
            response = session.get(
                KLINE_URL, 
                params=params,
                verify=False,
                timeout=30,  # 增加超时时间
                headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Accept-Encoding': 'gzip, deflate'
                }
            )
            
            if response.status_code == 200:
                klines = response.json()
                df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                                                 'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                                                 'taker_buy_quote', 'ignore'])
                
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                return df
            else:
                logger.warning(f"尝试 {attempt + 1}/{max_retries}: {symbol} 请求返回状态码 {response.status_code}")
                
        except Exception as e:
            logger.warning(f"尝试 {attempt + 1}/{max_retries}: {symbol} 请求错误: {e}")
            if attempt == max_retries - 1:
                logger.error(f"获取{symbol}数据失败: {e}")
                return None
        
        time.sleep(2 ** attempt)
    
    return None

def calculate_3h_klines(df_1h):
    """将1小时K线转换为3小时K线"""
    try:
        if df_1h is None or df_1h.empty:
            return None
        df_1h.set_index('timestamp', inplace=True)
        df_3h = df_1h.resample('3h').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        })
        return df_3h.reset_index()
    except Exception:
        return None

def get_all_symbols(max_retries=3):
    """获取所有可交易的永续合约币对，添加重试机制"""
    for attempt in range(max_retries):
        try:
            response = requests.get(
                EXCHANGE_INFO_URL,
                verify=True,
                timeout=10,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            
            if response.status_code == 200:
                data = response.json()
                symbols = [symbol['symbol'] for symbol in data['symbols'] 
                          if symbol['status'] == 'TRADING' and symbol['contractType'] == 'PERPETUAL']
                return symbols
                
        except Exception as e:
            logger.warning(f"尝试 {attempt + 1}/{max_retries}: 获取币对列表失败: {e}")
            if attempt == max_retries - 1:
                logger.error(f"获取币对列表失败: {e}")
                return []
        
        time.sleep(2 ** attempt)
    
    return []

def calculate_ema(df, period=21):
    """计算EMA指标"""
    try:
        if df is None or df.empty or len(df) < period:
            return None
        df['EMA21'] = df['close'].ewm(span=period, adjust=False).mean()
        return df
    except Exception:
        return None

def format_alert_message(symbol, price, ema, cross_type):
    """格式化警报消息为JSON格式"""
    deviation = ((price/ema - 1) * 100)
    icon = "🔴" if cross_type == "下破" else "🟢"
    alert_data = {
        "symbol": symbol,
        "alert_type": f"价格{cross_type}3h EMA21警报",
        "icon": icon,
        "price": round(price, 4),
        "ema21": round(ema, 4),
        "deviation": round(deviation, 2),
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    return json.dumps(alert_data, ensure_ascii=False, indent=4)

def send_feishu_alert(message):
    """发送飞书警报"""
    try:
        headers = {'Content-Type': 'application/json'}
        payload = {
            "msg_type": "text",
            "content": {"text": message}  # 直接发送JSON格式的消息
        }
        requests.post(FEISHU_WEBHOOK, headers=headers, data=json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        logger.error(f"发送警报失败: {e}")

def subscribe_klines(ws):
    """订阅K线数据"""
    symbols = get_all_symbols()
    subscribe_message = {
        "method": "SUBSCRIBE",
        "params": [
            f"{symbol.lower()}@kline_1h" for symbol in symbols  # 订阅1小时K线
        ],
        "id": 1
    }
    ws.send(json.dumps(subscribe_message))

def on_message(ws, message):
    """处理WebSocket消息"""
    try:
        data = json.loads(message)
        
        # 处理K线数据
        if 'e' in data and data['e'] == 'kline':
            symbol = data['s']
            kline = data['k']
            
            # 更新K线数据
            if symbol in kline_data:
                df = kline_data[symbol]
                if df is not None:
                    # 更新最新K线
                    df.loc[df.index[-1], 'close'] = float(kline['c'])
                    df.loc[df.index[-1], 'high'] = max(float(kline['h']), df.loc[df.index[-1], 'high'])
                    df.loc[df.index[-1], 'low'] = min(float(kline['l']), df.loc[df.index[-1], 'low'])
                    df.loc[df.index[-1], 'volume'] = float(kline['v'])
                    
                    # 计算EMA
                    df = calculate_ema(df)
                    if df is not None:
                        current_price = float(kline['c'])
                        current_ema = float(df['EMA21'].iloc[-1])
                        current_position = "above" if current_price > current_ema else "below"
                        
                        # 检查是否发生穿越
                        if symbol in position_records and current_position != position_records[symbol]:
                            current_time = time.time()
                            last_alert_time = last_alert_times.get(symbol, 0)
                            
                            if current_time - last_alert_time > alert_cooldown:
                                cross_type = "上破" if current_position == "above" else "下破"
                                message = format_alert_message(symbol, current_price, current_ema, cross_type)
                                send_feishu_alert(message)
                                last_alert_times[symbol] = current_time
                                logger.info(f"{symbol} {cross_type}EMA21")
                        
                        # 更新位置记录
                        position_records[symbol] = current_position
        
        # 处理实时成交数据
        elif 'e' in data and data['e'] == 'aggTrade':
            symbol = data['s']
            price = float(data['p'])
            # 更新最新价格
            if symbol in kline_data:
                df = kline_data[symbol]
                if df is not None:
                    df.loc[df.index[-1], 'close'] = price
                    
    except Exception as e:
        logger.error(f"处理WebSocket消息失败: {e}")

def on_error(ws, error):
    logger.error(f"WebSocket错误: {error}")

def on_close(ws, close_status_code, close_msg):
    logger.info("WebSocket连接关闭")

def on_open(ws):
    logger.info("WebSocket连接建立")
    # 订阅K线和实时成交数据
    subscribe_message = {
        "method": "SUBSCRIBE",
        "params": [],
        "id": 1
    }
    
    symbols = get_all_symbols()
    for symbol in symbols:
        symbol_lower = symbol.lower()
        subscribe_message["params"].extend([
            f"{symbol_lower}@kline_1h",  # 1小时K线
            f"{symbol_lower}@aggTrade"   # 实时成交
        ])
    
    ws.send(json.dumps(subscribe_message))
    logger.info("已订阅所有交易对的K线和实时成交数据")

def main():
    """主函数"""
    retry_count = 0
    max_retries = 10
    
    while True:
        try:
            # 初始化WebSocket连接
            websocket.enableTrace(True)
            ws = websocket.WebSocketApp(
                WS_URL,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )
            
            # WebSocket连接设置
            ws.run_forever(
                ping_interval=20,
                ping_timeout=10,
                reconnect=3,
                sslopt={"cert_reqs": ssl.CERT_NONE},
                sockopt=((socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),)
            )
            
        except WebSocketConnectionClosedException:
            retry_count += 1
            wait_time = min(retry_count * 5, 60)
            logger.warning(f"WebSocket连接断开，{wait_time}秒后重试... (尝试 {retry_count}/{max_retries})")
            time.sleep(wait_time)
            
            if retry_count >= max_retries:
                logger.error("达到最大重试次数，重启程序...")
                return
                
        except Exception as e:
            logger.error(f"WebSocket错误: {e}")
            time.sleep(10)
            
        logger.info("正在尝试重新连接...")

if __name__ == "__main__":
    while True:
        try:
            main()
            time.sleep(10)
        except KeyboardInterrupt:
            logger.info("程序正常退出")
            break
        except Exception as e:
            logger.error(f"程序异常退出: {e}")
            time.sleep(10)
