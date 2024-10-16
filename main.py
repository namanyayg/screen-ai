"""
"screen-ai" captures screenshots, performs OCR using OpenAI's API,
and interacts with a Vapi assistant to allow the user to talk to their
computer and discuss what's on the screen.

Use the shortcut Ctrl+Shift+O to start talking to your computer.
"""

import os
import sys
import logging
from typing import Optional

import base64
import math
import requests
from dotenv import load_dotenv
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QBrush, QPen, QColor, QKeySequence, QPainterPath
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QShortcut, QMessageBox
from mss import mss
from PIL import Image

from vapi_python import Vapi

# Set up logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class Config:
    def __init__(self):
        load_dotenv()
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.vapi_api_key = os.getenv('VAPI_API_KEY')
        self.vapi_assistant_id = os.getenv("VAPI_ASSISTANT_ID", "ea8c30ba-4efb-4b3a-b3fa-9cd37a821300")
        self.validate()
    
    def validate(self):
        missing_vars = []
        for var in ['openai_api_key', 'vapi_api_key']:
            if not getattr(self, var):
                missing_vars.append(var)
        
        if missing_vars:
            error_msg = f"Missing environment variables: {', '.join(missing_vars)}"
            logger.error(error_msg)
            QMessageBox.critical(None, "Configuration Error", error_msg)
            sys.exit(1)

# Instantiate config
config = Config()

class ScreenCapture:
    @staticmethod
    def capture_and_save():
        """Take a screenshot using mss and save it."""
        screenshot_path = os.path.join(os.getcwd(), 'screenshot.jpg')
        try:
            with mss() as sct:
                # Capture entire screen
                monitor = sct.monitors[0]
                sct_img = sct.grab(monitor)
                
                # Convert to PIL Image
                img = Image.frombytes('RGB', sct_img.size, sct_img.bgra, 'raw', 'BGRX')
                
                # Save as JPEG
                img.save(screenshot_path, 'JPEG')
            
            logger.info(f"Screenshot saved to {screenshot_path}")
            return screenshot_path
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            return None

class OCRProcessor:
    @staticmethod
    def process(screenshot_path: str) -> Optional[str]:
        """Perform OCR on the screenshot using OpenAI's API."""
        try:
            with open(screenshot_path, 'rb') as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
                
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.openai_api_key}"
            }
            payload = {
                "model": "gpt-4-turbo",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Give a summary of what's in the image after 'SUMMARY:' "
                                        "and give full OCR exactly and correctly without any "
                                        "missing details after 'OCR:'"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{encoded_image}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 300
            }

            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            logger.info("OCR processing completed successfully")
            return response.json()['choices'][0]['message']['content']
        except Exception as e:
            logger.error(f"Error performing OCR: {e}")
            return None

class VapiManager:
    def __init__(self):
        self.vapi = Vapi(api_key=config.vapi_api_key)

    def start(self, screen_data: str):
        """Start the Vapi assistant with the given screen data."""
        assistant_overrides = {
            "variableValues": {
                "screendata": screen_data
            }
        }
        logger.info("Starting Vapi assistant")
        self.vapi.start(assistant_id=config.vapi_assistant_id, assistant_overrides=assistant_overrides)

class UIManager:
    def __init__(self, parent):
        self.parent = parent
        self.pulse_timer: Optional[QTimer] = None
        self.pulse_frame: int = 0

    def setup(self):
        """Initialize the user interface components."""
        self.parent.setWindowTitle('Screen AI')
        self.parent.setGeometry(100, 100, 300, 300)
        self.parent.show()

        # Shortcut to trigger screenshot and OCR
        self.shortcut = QShortcut(QKeySequence('Ctrl+Shift+O'), self.parent)
        self.shortcut.activated.connect(self.parent.capture_and_process)
        logger.info("UI setup completed")

    def paint(self, painter: QPainter):
        """Handle the paint event to draw the UI."""
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(Qt.black, 8, Qt.SolidLine))
        painter.setBrush(QBrush(Qt.black, Qt.SolidPattern))

        center_x, center_y = 150, 150
        circle_radius = 120

        if self.parent.state == 'talking':
            radius_variation = 10 * (1 + math.sin(self.pulse_frame * math.pi / 100))
            radius = circle_radius + radius_variation
        else:
            radius = circle_radius

        painter.drawEllipse(int(center_x - radius / 2), int(center_y - radius / 2), int(radius), int(radius))

    def update_state(self, new_state: str):
        """Update the state of the application and manage the pulse timer."""
        self.parent.state = new_state
        if new_state == 'talking':
            self.pulse_frame = 0
            self.pulse_timer = QTimer(self.parent)
            self.pulse_timer.timeout.connect(self.pulse_circle)
            self.pulse_timer.start(10)
        elif self.pulse_timer is not None:
            self.pulse_timer.stop()
            self.pulse_timer = None
        self.parent.update()
        logger.info(f"Application state updated to: {new_state}")

    def pulse_circle(self):
        """Update the pulse frame and trigger a repaint."""
        self.pulse_frame = (self.pulse_frame + 1) % 200
        self.parent.update()

class ScreenAI(QWidget):
    def __init__(self):
        super().__init__()
        self.state: str = 'idle'  # Possible states: 'loading', 'talking', 'idle'
        self.ui_controller = UIManager(self)
        self.screen_capture = ScreenCapture()
        self.ocr_processor = OCRProcessor()
        self.vapi_assistant = VapiManager()
        self.ui_controller.setup()
        logger.info("ScreenAI initialized")

    def paintEvent(self, event):
        """Handle the paint event to draw the UI."""
        painter = QPainter(self)
        self.ui_controller.paint(painter)

    def capture_and_process(self):
        """Take a screenshot, perform OCR, and start Vapi."""
        logger.info("Starting OCR process...")
        self.ui_controller.update_state('loading')
        screenshot_path = self.screen_capture.capture_and_save()
        if screenshot_path:
            screen_data = self.ocr_processor.process(screenshot_path)
            if screen_data:
                self.ui_controller.update_state('talking')
                self.vapi_assistant.start(screen_data)
                logger.info(f"OCR Result:\n{screen_data}")
            else:
                logger.error("OCR failed. Unable to start Vapi.")
                self.ui_controller.update_state('idle')
        else:
            logger.error("Failed to take screenshot. Unable to proceed.")
            self.ui_controller.update_state('idle')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ScreenAI()
    sys.exit(app.exec_())