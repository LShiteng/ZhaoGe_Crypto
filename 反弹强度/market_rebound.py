import pandas as pd
from pycoingecko import CoinGeckoAPI
from datetime import datetime, timedelta
import time
import pytz

def is_derivative_token(symbol, id):
    """判断是否为衍生代币或稳定币"""
    # 转换为大写进行比较
    symbol = symbol.upper()
    id = id.lower()
    
    # 需要排除的代币类型列表
    exclude_tokens = {
        # 衍生代币
        'SOL': ['BNSOL', 'WSOL', 'STSOL', 'MSOL'],
        'BTC': ['WBTC', 'SBTC', 'HBTC', 'BTCB', 'SOLVBTC'],
        'ETH': ['WETH', 'SETH', 'STETH', 'BETH'],
        
        # 稳定币及其变体
        'STABLE': [
            'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'UST', 'USDP', 'USDD', 'GUSD', 'FRAX',
            'FDUSDT', 'USDE', 'USD0', 'USDB', 'USDX', 'USDD', 'USDJ', 'USDN', 'USDH',
            'USDK', 'USDL', 'USDM', 'USDR', 'USDS', 'USDY', 'USDV', 'USDW', 'USDZ',
            'DAI', 'SAI', 'RAI', 'VAI', 'MAI', 'HAI', 'PAI', 'TAI', 'KAI',
            'SUSD', 'NUSD', 'MUSD', 'LUSD', 'HUSD', 'FUSD', 'EUSD', 'DUSD',
            'CUSD', 'BUSD', 'AUSD', 'RUSD', 'PUSD', 'OUSD', 'IUSD', 'YUSD',
            'TUSD', 'ZUSD', 'XUSD', 'WUSD', 'VUSD', 'QUSD'
        ]
    }
    
    # 检查是否在排除列表中
    for _, tokens in exclude_tokens.items():
        if symbol in tokens:
            return True
    
    # 检查代币ID中的关键词
    exclude_keywords = [
        'wrapped', 'staked', 'synthetic', 'leveraged',
        'stable', 'usd', 'dollar', 'peg', 'fixed',
        'dai', 'tether', 'usdt', 'usdc'
    ]
    
    if any(keyword in id for keyword in exclude_keywords):
        return True
        
    # 检查代币符号是否包含USD或稳定币相关关键词
    if 'USD' in symbol or 'DAI' in symbol or 'STABLE' in symbol:
        return True
        
    return False

def get_coins_until_100_valid():
    """获取足够数量的非衍生代币"""
    cg = CoinGeckoAPI()
    valid_coins = []
    page = 1
    per_page = 250  # 每页获取更多数据以提高效率
    processed_count = 0
    
    while len(valid_coins) < 100:
        try:
            coins = cg.get_coins_markets(
                vs_currency='usd',
                order='market_cap_desc',
                per_page=per_page,
                page=page
            )
            
            if not coins:  # 如果没有更多数据了
                break
                
            for coin in coins:
                processed_count += 1
                print(f"正在检查第 {processed_count} 个币种: {coin['symbol'].upper()}")
                
                if not is_derivative_token(coin['symbol'], coin['id']):
                    if coin['symbol'].upper() in ['BTC', 'ETH', 'SOL']:
                        valid_coins.append((coin['id'], coin['symbol'].upper()))
                    elif len(valid_coins) < 100:  # 只有在还没收集够100个时才添加其他币种
                        valid_coins.append((coin['id'], coin['symbol'].upper()))
            
            page += 1
            time.sleep(0.5)  # 避免API限制
            
        except Exception as e:
            print(f"获取币种列表时出错: {str(e)}")
            break
    
    print(f"共处理了 {processed_count} 个币种，获取到 {len(valid_coins)} 个有效币种")
    return valid_coins[:100]  # 返回前100个有效币种

def get_coin_data(coin_id, start_timestamp, end_timestamp):
    """获取币种在指定时间段的价格数据"""
    cg = CoinGeckoAPI()
    try:
        # CoinGecko API要求时间戳为秒
        prices = cg.get_coin_market_chart_range_by_id(
            id=coin_id,
            vs_currency='usd',
            from_timestamp=start_timestamp,
            to_timestamp=end_timestamp
        )
        
        if not prices['prices']:
            return None
            
        df = pd.DataFrame(prices['prices'], columns=['timestamp', 'price'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
        
    except Exception as e:
        print(f"获取 {coin_id} 数据时出错: {str(e)}")
        return None

def convert_to_utc(beijing_time_str):
    """将北京时间转换为UTC时间"""
    beijing_tz = pytz.timezone('Asia/Shanghai')
    utc_tz = pytz.UTC
    
    beijing_time = beijing_tz.localize(datetime.strptime(beijing_time_str, '%Y-%m-%d %H:%M:%S'))
    utc_time = beijing_time.astimezone(utc_tz)
    
    return utc_time

def get_current_valid_time():
    """获取当前有效的时间范围"""
    current_time = datetime.now(pytz.UTC)
    valid_end_time = current_time
    valid_start_time = valid_end_time - timedelta(days=1)  # 获取24小时前的数据
    return valid_start_time, valid_end_time

def calculate_rebound_strength(df, start_time, end_time=None):
    """计算指定时间范围内的反弹强度"""
    if df is None or df.empty:
        return None, None, None, None, None, None
    
    try:
        # 确保时间类型一致，转换为pandas的Timestamp
        start_time = pd.Timestamp(start_time).tz_localize(None)  # 移除时区信息
        if end_time is not None:
            end_time = pd.Timestamp(end_time).tz_localize(None)
        
        # 移除DataFrame中timestamp的时区信息
        df['timestamp'] = df['timestamp'].dt.tz_localize(None)
        
        # 过滤时间范围
        mask = df['timestamp'] >= start_time
        if end_time is not None:
            mask &= df['timestamp'] <= end_time
        df_filtered = df[mask]
        
        if df_filtered.empty:
            return None, None, None, None, None, None
        
        low_price = df_filtered['price'].min()
        high_price = df_filtered['price'].max()
        last_price = df_filtered['price'].iloc[-1]
        
        low_time = df_filtered.loc[df_filtered['price'] == low_price, 'timestamp'].iloc[0]
        high_time = df_filtered.loc[df_filtered['price'] == high_price, 'timestamp'].iloc[0]
        
        max_rebound = ((high_price - low_price) / low_price) * 100
        current_rebound = ((last_price - low_price) / low_price) * 100
        
        return low_price, high_price, max_rebound, current_rebound, low_time, high_time
        
    except Exception as e:
        print(f"计算反弹强度时出错: {str(e)}")
        return None, None, None, None, None, None

def get_main_coins():
    """只获取BTC、ETH和SOL的数据"""
    main_coins = [
        ('bitcoin', 'BTC'),
        ('ethereum', 'ETH'),
        ('solana', 'SOL')
    ]
    return main_coins

def format_price(price):
    """格式化价格，去除多余的0"""
    if price is None:
        return None
    # 转换为字符串并去除尾部的0
    formatted = f"{price:.8f}".rstrip('0').rstrip('.')
    return formatted

def analyze_market_rebound(period1_start, period1_end, period2_end):
    """分析两个时间段的市场反弹情况"""
    start_timestamp = int(period1_start.timestamp())
    end_timestamp = int(period2_end.timestamp())
    
    results = []
    print("正在获取币种数据...")
    coins = get_coins_until_100_valid()
    
    # 创建已处理币种集合，用于去重
    processed_symbols = set()
    total_coins = len(coins)
    print(f"成功获取 {total_coins} 个有效币种")
    
    for idx, (coin_id, symbol) in enumerate(coins, 1):
        # 跳过重复的币种
        if symbol in processed_symbols:
            continue
        processed_symbols.add(symbol)
        
        print(f"正在处理 {symbol}... ({idx}/{total_coins})")
        
        try:
            df = get_coin_data(coin_id, start_timestamp, end_timestamp)
            
            if df is not None:
                result1 = calculate_rebound_strength(df.copy(), period1_start, period1_end)
                result2 = calculate_rebound_strength(df.copy(), period1_start, period2_end)
                
                if result1[0] is not None and result2[0] is not None:
                    results.append({
                        '币种': symbol,
                        '最低点($)': format_price(result1[0]),
                        '最高点($)': format_price(result1[1]),
                        '最高点反弹(%)': round(result1[2], 2),
                        '2.5 17:00反弹(%)': round(result2[3], 2),
                    })
        except Exception as e:
            print(f"处理 {symbol} 时出错: {str(e)}")
            continue
        
        time.sleep(0.5)
    
    df_results = pd.DataFrame(results)
    if not df_results.empty:
        df_results = df_results.sort_values('最高点反弹(%)', ascending=False)
    
    return df_results

def export_to_excel(df, filename):
    """导出到Excel"""
    try:
        writer = pd.ExcelWriter(filename, engine='openpyxl')
        df.to_excel(writer, index=False, sheet_name='反弹分析')
        
        worksheet = writer.sheets['反弹分析']
        
        # 更新列宽以适应新的表头
        column_widths = {
            'A': 10,   # 币种
            'B': 15,   # 最低点
            'C': 15,   # 最高点
            'D': 15,   # 最高点反弹
            'E': 18,   # 2.5 17:00反弹
        }
        
        for col, width in column_widths.items():
            worksheet.column_dimensions[col].width = width
        
        writer.close()
        print(f"数据已导出到 {filename}")
        
    except Exception as e:
        print(f"导出Excel时出错: {str(e)}")
        csv_filename = filename.replace('.xlsx', '.csv')
        df.to_csv(csv_filename, index=False)
        print(f"已将数据导出为CSV格式: {csv_filename}")

def main():
    # 定义北京时间
    period1_start_bj = '2025-02-03 02:00:00'  # 改为2月3日2:00
    period1_end_bj = '2025-02-04 06:00:00'
    period2_end_bj = '2025-02-05 17:00:00'    # 改为2月5日17:00
    
    # 转换为UTC时间
    period1_start_utc = convert_to_utc(period1_start_bj)
    period1_end_utc = convert_to_utc(period1_end_bj)
    period2_end_utc = convert_to_utc(period2_end_bj)
    
    print(f"分析时间范围1: {period1_start_bj} 到 {period1_end_bj} (北京时间)")
    print(f"分析时间范围2: {period1_start_bj} 到 {period2_end_bj} (北京时间)")
    
    print("开始获取数据...")
    results_df = analyze_market_rebound(period1_start_utc, period1_end_utc, period2_end_utc)
    
    # 导出结果
    current_time = datetime.now()
    filename = f'加密货币反弹分析_{current_time.strftime("%Y%m%d_%H%M%S")}.xlsx'
    export_to_excel(results_df, filename)
    print("分析完成！")

if __name__ == "__main__":
    main() 