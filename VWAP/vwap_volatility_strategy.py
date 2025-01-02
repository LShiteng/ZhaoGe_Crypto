# 导入所需的库
from datetime import datetime, timedelta, timezone  # 用于处理日期和时间
import requests  # 用于发送HTTP请求
import numpy as np  # 用于科学计算
from tqdm import tqdm  # 用于显示进度条
import time  # 用于时间相关操作
import concurrent.futures  # 用于并行处理
from requests.adapters import HTTPAdapter  # 用于HTTP请求的重试机制
from requests.packages.urllib3.util.retry import Retry  # 用于定义重试策略
import logging  # 用于日志记录
import urllib3  # HTTP客户端
import certifi  # 提供Mozilla的根证书包
import traceback  # 用于异常追踪

# 设置SSL证书
urllib3.util.ssl_.DEFAULT_CERTS = certifi.where()

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 设置Binance API的基础URL
BASE_URL = "https://fapi.binance.com"

# 定义一个函数，用于创建一个带有重试机制的请求会话
def requests_retry_session(
    retries=10,  # 重试次数
    backoff_factor=1,  # 重试间隔的增长因子
    status_forcelist=(500, 502, 504, 520, 524, 429),  # 需要重试的HTTP状态码
    session=None,  # 可选的会话对象
):
    """
    创建一个带有重试机制的requests会话
    
    参数:
    retries: 最大重试次数
    backoff_factor: 重试之间的延迟时间
    status_forcelist: 需要重试的HTTP状态码列表
    session: 现有的session对象（如果没有则创建新的）
    
    返回:
    配置了重试机制的requests.Session对象
    """
    session = session or requests.Session()  # 如果没有提供会话对象，则创建一个新的会话
    retry = Retry(
        total=retries,  # 总重试次数
        read=retries,  # 读取超时重试次数
        connect=retries,  # 连接超时重试次数
        backoff_factor=backoff_factor,  # 重试间隔的增长因子
        status_forcelist=status_forcelist,  # 需要重试的HTTP状态码
    )
    adapter = HTTPAdapter(max_retries=retry)  # 创建一个带有重试策略的HTTP适配器
    session.mount('http://', adapter)  # 将HTTP适配器挂载到会话上
    session.mount('https://', adapter)  # 将HTTPS适配器挂载到会话上
    session.verify = False  # 禁用SSL证书验证
    requests.packages.urllib3.disable_warnings()  # 禁用urllib3的警告
    return session  # 返回配置好的会话对象

# 定义一个函数，用于获取交易所信息
def get_exchange_info():
    """获取交易所信息"""
    response = requests_retry_session().get(f"{BASE_URL}/fapi/v1/exchangeInfo")  # 发送GET请求获取交易所信息
    return response.json()  # 返回JSON格式的响应

# 定义一个函数，用于获取所有交易对的当前价格
def get_all_symbol_prices():
    """获取所有交易对的当前价格"""
    response = requests_retry_session().get(f"{BASE_URL}/fapi/v2/ticker/price")  # 发送GET请求获取所有交易对的当前价格
    return {item['symbol']: float(item['price']) for item in response.json()}  # 返回一个字典，键是交易对名称，值是当前价格

# 定义一个函数，用于获取OHLCV数据
def fetch_ohlcv(symbol, interval, limit):
    """
    获取OHLCV（开盘价、最高价、最低价、收盘价、成交量）数据
    
    参数:
    symbol: 交易对符号
    interval: 时间间隔
    limit: 获取的数据点数量
    
    返回:
    包含OHLCV数据的DataFrame
    """
    params = {
        "symbol": symbol,  # 交易对名称
        "interval": interval,  # 时间间隔
        "limit": limit  # 数据点数量限制
    }
    response = requests_retry_session().get(f"{BASE_URL}/fapi/v1/klines", params=params)  # 发送GET请求获取OHLCV数据
    klines = response.json()  # 获取JSON格式的响应
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])  # 创建一个DataFrame
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)  # 将时间戳转换为日期时间格式
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()  # 使用copy()避免SettingWithCopyWarning
    df = df.astype({'open': float, 'high': float, 'low': float, 'close': float, 'volume': float})  # 将数据类型转换为浮点数
    df.set_index('timestamp', inplace=True)  # 将时间戳设置为索引
    return df  # 返回DataFrame

# 定义一个函数，用于计算VWAP和标准差
def calculate_vwap(df):
    """计算VWAP和标准差"""
    df.loc[:, 'hlc3'] = (df['high'] + df['low'] + df['close']) / 3  # 计算HLC3
    df.loc[:, 'vwap'] = (df['hlc3'] * df['volume']).cumsum() / df['volume'].cumsum()  # 计算VWAP
    df.loc[:, 'sumSrcSrcVol'] = (df['volume'] * df['hlc3'] ** 2).cumsum()  # 计算成交量的平方和
    df.loc[:, 'variance'] = df['sumSrcSrcVol'] / df['volume'].cumsum() - df['vwap'] ** 2  # 计算方差
    df.loc[:, 'variance'] = df['variance'].apply(lambda x: max(x, 0))  # 将负方差设置为0
    df.loc[:, 'stDev'] = np.sqrt(df['variance'])  # 计算标准差
    return df['vwap'].iloc[-1], df['stDev'].iloc[-1]  # 返回最后一个VWAP和标准差

# 定义一个函数，用于计算VAH和VAL
def calculate_vah_val(df, stDev, stDevMultiplier_1=1.0, stDevMultiplier_2=2.0):
    """计算VAH和VAL"""
    vwap = df['vwap'].iloc[-1]
    vah = vwap + stDev * stDevMultiplier_1
    val = vwap - stDev * stDevMultiplier_1
    return vah, val

def is_new_period(now, period):
    """判断是否是新的时间周期"""
    if period == 'week':
        return now.weekday() == 0 and now.hour == 0
    elif period == 'month':
        return now.day == 1 and now.hour == 0
    elif period == 'quarter':
        return now.month in [1, 4, 7, 10] and now.day == 1 and now.hour == 0
    elif period == 'year':
        return now.month == 1 and now.day == 1 and now.hour == 0
    return False

def calculate_metrics(symbol, current_period=True):
    """计算各个时间维度的指标"""
    now = datetime.now(timezone.utc)
    if current_period:
        start_of_week = now - timedelta(days=now.weekday())
        start_of_month = now.replace(day=1)
        start_of_quarter = now.replace(month=((now.month - 1) // 3) * 3 + 1, day=1)
        start_of_year = now.replace(month=1, day=1)
        timeframes = {
            'week': ('1h', 168),
            'month': ('1d', 30),
            'quarter': ('1d', 90),
            'year': ('1d', 365)
        }
        start_times = {
            'week': start_of_week,
            'month': start_of_month,
            'quarter': start_of_quarter,
            'year': start_of_year
        }
    else:
        start_of_week = now - timedelta(days=now.weekday(), weeks=1)
        start_of_month = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
        start_of_quarter = (now.replace(month=((now.month - 1) // 3) * 3 + 1, day=1) - timedelta(days=1)).replace(month=((now.month - 1) // 3) * 3 + 1, day=1)
        start_of_year = (now.replace(month=1, day=1) - timedelta(days=1)).replace(month=1, day=1)
        timeframes = {
            'week': ('1h', 168),
            'month': ('1d', 30),
            'quarter': ('1d', 90),
            'year': ('1d', 365)
        }
        start_times = {
            'week': start_of_week,
            'month': start_of_month,
            'quarter': start_of_quarter,
            'year': start_of_year
        }
    
    metrics = {}
    
    for period, (interval, limit) in timeframes.items():
        df = fetch_ohlcv(symbol, interval, limit)
        df = df[df.index >= start_times[period]].copy()  # 明确创建一个副本
        
        if df.empty:
            continue
        
        vwap, stDev = calculate_vwap(df)
        vah, val = calculate_vah_val(df, stDev)
        
        metrics[period] = {
            'vwap': vwap,
            'vah': vah,
            'val': val,
            'is_new_period': is_new_period(now, period) if current_period else False
        }
    
    return metrics

def calculate_weight(symbol, current_metrics, previous_metrics, current_price):
    """计算权重"""
    current_weight = 0
    previous_weight = 0
    
    key_levels = ['val', 'vwap', 'vah']
    time_weights = {'week': 1, 'month': 2, 'quarter': 3, 'year': 4}
    
    # 检查月度VWAP波动值
    if 'month' in current_metrics:
        month_vah = current_metrics['month']['vah']
        month_val = current_metrics['month']['val']
        if not np.isnan(month_vah) and not np.isnan(month_val):
            if (month_vah - month_val) / current_price < 0.01:
                return 1, 1, 2
    
    # 计算当前周期的权重
    for period in current_metrics.keys():
        period_weight = 0
        for level in key_levels:
            if level in current_metrics[period] and not np.isnan(current_metrics[period][level]):
                if abs(current_price - current_metrics[period][level]) / current_metrics[period][level] < 0.01:
                    period_weight += 1
        
        if not np.isnan(current_metrics[period]['val']) and not np.isnan(current_metrics[period]['vwap']) and not np.isnan(current_metrics[period]['vah']):
            if current_price < current_metrics[period]['val']:
                period_weight += 1
            elif current_metrics[period]['vwap'] > current_price > current_metrics[period]['val']:
                period_weight += 2
            elif current_metrics[period]['vah'] > current_price > current_metrics[period]['vwap']:
                period_weight += 3
            elif current_price > current_metrics[period]['vah']:
                period_weight += 4
        
        current_weight += period_weight * time_weights[period]
    
    # 计算上一周期的权重
    for period in previous_metrics.keys():
        period_weight = 0
        p_val = previous_metrics[period]['val']
        p_vwap = previous_metrics[period]['vwap']
        p_vah = previous_metrics[period]['vah']
        
        if not np.isnan(p_val) and not np.isnan(p_vwap) and not np.isnan(p_vah):
            if current_price < p_val:
                period_weight += 1
            elif p_vwap > current_price > p_val:
                period_weight += 2
            elif p_vah > current_price > p_vwap:
                period_weight += 3
            elif current_price > p_vah:
                period_weight += 4
        
        previous_weight += period_weight * time_weights[period]
    
    # 根据现周期和上周期的权重关系确定权重系数
    alpha, beta = 0.6, 0.4
    
    # 计算总权重
    total_weight = alpha * current_weight + beta * previous_weight
    
    return current_weight, previous_weight, total_weight

def send_to_feishu(results):
    """发送结果到飞书"""
    webhook_url = "https://www.feishu.cn/flow/api/trigger-webhook/e8dcc2688bf699aef589e722e8ade93b"
    headers = {
        "Content-Type": "application/json"
    }
    
    # 按总权重排序
    sorted_results = sorted(results, key=lambda x: x['total_weight'], reverse=True)
    
    # 构建消息内容
    message_content = ""
    for i, result in enumerate(sorted_results[:100], 1):
        symbol = result['symbol'].replace('USDT', '/USDT')
        message_content += f"{i}.{symbol}--总权重值: {result['total_weight']:.2f}\n"
    
    message = {
        "msg_type": "text",
        "content": {
            "text": message_content
        }
    }
    
    response = requests.post(webhook_url, headers=headers, json=message)
    if response.status_code == 200:
        print("结果已成功发送到飞书")
    else:
        print(f"发送到飞书失败，状态码：{response.status_code}")

def get_24h_volume(symbol):
    """获取交易对24小时成交量"""
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = requests_retry_session().get(f"{BASE_URL}/fapi/v1/ticker/24hr", params={'symbol': symbol}, timeout=30)
            response.raise_for_status()
            return float(response.json()['volume'])
        except requests.exceptions.RequestException as e:
            logger.warning(f"获取 {symbol} 24小时成交量时出错 (尝试 {attempt+1}/{max_retries}): {e}")
            logger.debug(f"错误详情: {traceback.format_exc()}")
            if attempt == max_retries - 1:
                logger.error(f"获取 {symbol} 24小时成交量失败，已达到最大重试次数")
                logger.debug(f"最后一次错误详情: {traceback.format_exc()}")
                return 0
        time.sleep(2 ** attempt)
    return 0

def process_symbol(symbol, current_price):
    try:
        current_metrics = calculate_metrics(symbol, current_period=True)
        previous_metrics = calculate_metrics(symbol, current_period=False)
        
        current_weight, previous_weight, total_weight = calculate_weight(symbol, current_metrics, previous_metrics, current_price)
        
        result = {
            'symbol': symbol,
            'current_price': current_price,
            'current_weight': current_weight,
            'previous_weight': previous_weight,
            'total_weight': total_weight,
            'current_metrics': current_metrics,
            'previous_month_metrics': previous_metrics.get('month', {})
        }
        
        return result
    except Exception as e:
        logger.error(f"处理交易对 {symbol} 时出错: {e}")
        logger.debug(f"错误详情: {traceback.format_exc()}")
        return None

def main():
    try:
        # 获取所有交易对价格
        all_prices = get_all_symbol_prices()
        
        # 筛选USDT本位永续合约
        all_symbols = [
            symbol for symbol in all_prices.keys() 
            if symbol.endswith('USDT') 
            and not symbol.startswith('DEFI')
        ]
        
        # 设置最大交易对数量阈值
        MAX_SYMBOLS = 300
        if len(all_symbols) > MAX_SYMBOLS:
            logger.warning(f"获取到的交易对数量 ({len(all_symbols)}) 超过预期。将限制为前 {MAX_SYMBOLS} 个。")
            all_symbols = all_symbols[:MAX_SYMBOLS]
        
        # 打印获取到的交易对列表
        logger.info(f"获取到 {len(all_symbols)} 个交易对：{', '.join(all_symbols)}")
        
        logger.info(f"开始处理所有交易对")
        
        results = []
        
        # 使用多线程并行处理交易对
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_symbol, symbol, all_prices[symbol]): symbol for symbol in all_symbols}
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Processing symbols"):
                result = future.result()
                if result:
                    # 排除没有成交量的交易对
                    if get_24h_volume(result['symbol']) > 0:
                        results.append(result)
        
        if results:
            # 按总权重排序
            sorted_results = sorted(results, key=lambda x: x['total_weight'], reverse=True)
            
            # 发送权重排名前100名的交易对到飞书
            send_to_feishu(sorted_results[:100])
            
            # 打印前100个结果到控制台
            for i, result in enumerate(sorted_results[:100], 1):
                logger.info(f"{i}. {result['symbol']} - 总权重: {result['total_weight']:.2f}")
        else:
            logger.warning("没有成功处理任何交易对，不发送结果到飞书")
    except Exception as e:
        logger.error(f"主函数执行出错: {e}")
        logger.debug(f"错误详情: {traceback.format_exc()}")

if __name__ == "__main__":
    main()

