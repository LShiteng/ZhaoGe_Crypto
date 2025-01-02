import os
import time
import json
import logging
import schedule
import requests
import hashlib
from dotenv import load_dotenv
from pythonjsonlogger import jsonlogger
from datetime import datetime

# Configure logging
logger = logging.getLogger()
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)

# Load environment variables
load_dotenv()

# Configuration
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")
WEBSITE_URLS = [
    "https://juu17.com/en/home",
    "https://juu17.com/en/another-page",
    "https://juu17.com/en/yet-another-page"
]

class WebsiteMonitor:
    def __init__(self):
        self.last_content_hashes = {url: None for url in WEBSITE_URLS}
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def get_website_content(self, url):
        try:
            response = self.session.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Error fetching website content from {url}: {str(e)}")
            return None

    def check_for_updates(self):
        for url in WEBSITE_URLS:
            content = self.get_website_content(url)
            if not content:
                continue

            current_hash = hashlib.md5(content.encode()).hexdigest()
            
            if self.last_content_hashes[url] is None:
                self.last_content_hashes[url] = current_hash
                logger.info(f"Initial content hash recorded for {url}")
                continue

            if current_hash != self.last_content_hashes[url]:
                self.last_content_hashes[url] = current_hash
                message = f"Website Update Detected!\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nURL: {url}"
                self.send_feishu_message(message)
                logger.info(f"Website update detected for {url} and notification sent")

    def send_feishu_message(self, message):
        """Send message to Feishu"""
        if not FEISHU_WEBHOOK:
            logger.error("Feishu webhook not configured")
            return
        
        try:
            data = {
                "msg_type": "text",
                "content": {
                    "text": message
                }
            }
            response = requests.post(FEISHU_WEBHOOK, json=data)
            if response.status_code == 200:
                logger.info("Message sent to Feishu successfully")
            else:
                logger.error(f"Failed to send message to Feishu: {response.text}")
        except Exception as e:
            logger.error(f"Error sending message to Feishu: {str(e)}")


def main():
    monitor = WebsiteMonitor()
    
    # Schedule task to check updates every 2 minutes
    schedule.every(2).minutes.do(monitor.check_for_updates)
    
    # Initial run
    monitor.check_for_updates()
    
    # Keep running scheduled tasks
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
