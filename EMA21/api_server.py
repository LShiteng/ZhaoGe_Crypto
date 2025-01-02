from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import threading
import json
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# 全局状态存储
monitoring_status = {
    'status': {
        'connection': '已连接',
        'active_symbols': 0,
        'last_update': '',
        'alerts_today': 0
    },
    'pairs': []
}

@app.route('/')
def index():
    """提供监控页面"""
    return send_from_directory('.', 'monitor.html')

@app.route('/api/status')
def get_status():
    return jsonify(monitoring_status)

def update_status(kline_data, position_records):
    """更新监控状态"""
    global monitoring_status
    pairs = []
    
    for symbol in kline_data:
        if symbol in position_records:
            df = kline_data[symbol]
            pairs.append({
                'symbol': symbol,
                'price': float(df['close'].iloc[-1]),
                'ema21': float(df['EMA21'].iloc[-1]),
                'deviation': round(((float(df['close'].iloc[-1]) / float(df['EMA21'].iloc[-1]) - 1) * 100), 2),
                'position': position_records[symbol]
            })
    
    monitoring_status['pairs'] = pairs
    monitoring_status['status']['active_symbols'] = len(pairs)
    monitoring_status['status']['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def run_api_server():
    app.run(host='0.0.0.0', port=5000) 