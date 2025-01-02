import os
import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

# Configuration
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")
LOGIN_URL = "https://juu17.com/en/home"  # Replace with actual login URL if needed

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup Chrome options
chrome_options = Options()
chrome_options.add_argument("--headless")  # Run headless Chrome
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

# Path to chromedriver
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "chromedriver")

class MessageMonitor:
    def __init__(self):
        self.driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=chrome_options)
        self.driver.get(LOGIN_URL)
        logger.info("Opened website for monitoring")

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

    def monitor_messages(self):
        try:
            while True:
                # Example: Wait for a specific element that signifies a new message
                try:
                    new_message_element = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "new-message-class"))  # Replace with actual class name
                    )
                    message_text = new_message_element.text
                    logger.info(f"New message detected: {message_text}")
                    self.send_feishu_message(f"New message: {message_text}")
                except TimeoutException:
                    logger.info("No new messages detected in this interval")

                time.sleep(30)  # Check every 30 seconds
        finally:
            self.driver.quit()

if __name__ == "__main__":
    monitor = MessageMonitor()
    monitor.monitor_messages()
