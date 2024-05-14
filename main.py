import sys
import os
import requests
import base64
import math
from vapi_python import Vapi
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QShortcut
from PyQt5.QtGui import QPainter, QBrush, QPen, QColor, QKeySequence, QPainterPath
from PyQt5.QtCore import Qt, QTimer
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

VAPI_ASSISTANT_ID = "ea8c30ba-4efb-4b3a-b3fa-9cd37a821300"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        vapi_api_key = os.getenv('VAPI_API_KEY')
        self.vapi = Vapi(api_key=vapi_api_key)
        self.state = 'idle'  # Possible states: 'loading', 'talking', 'idle'
        self.pulse_timer = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle('ggg-4o')
        self.setGeometry(100, 100, 300, 300)
        self.show()

        # Shortcut to trigger screenshot and OCR
        self.shortcut = QShortcut(QKeySequence('Ctrl+Shift+O'), self)
        self.shortcut.activated.connect(self.take_screenshot_and_ocr)
        # self.take_screenshot_and_ocr()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)  # Enable antialiasing for smooth edges
        painter.setPen(QPen(Qt.black, 8, Qt.SolidLine))
        painter.setBrush(QBrush(Qt.black, Qt.SolidPattern))

        center_x = 150  # Fixed center x-coordinate
        center_y = 150  # Fixed center y-coordinate

        # if self.state == 'loading':
            # painter.drawRect(350, 250, 100, 100)  # Draw a square
        if self.state == 'talking':
            # Draw a pulsating circle with smooth easing animation
            radius_variation = 10 * (1 + math.sin(self.pulse_frame * math.pi / 100))
            radius = 120 + radius_variation
            painter.drawEllipse(int(center_x - radius / 2), int(center_y - radius / 2), int(radius), int(radius))
        else:
            radius = 120
            painter.drawEllipse(int(center_x - radius / 2), int(center_y - radius / 2), int(radius), int(radius))

    def update_state(self, new_state):
        self.state = new_state
        if new_state == 'talking':
            self.pulse_frame = 0
            self.pulse_timer = QTimer(self)
            self.pulse_timer.timeout.connect(self.pulse_circle)
            self.pulse_timer.start(10)
        elif self.pulse_timer is not None:
            self.pulse_timer.stop()
            self.pulse_timer = None
        self.update()  # Trigger a repaint

    def pulse_circle(self):
        self.pulse_frame += 1
        if self.pulse_frame >= 200:
            self.pulse_frame = 0
        self.update()

    def take_and_save_screenshot(self):
        # Take screenshot using pyautogui
        os.system("""
            powershell.exe \"
                Add-Type -AssemblyName System.Windows.Forms
                [Windows.Forms.Sendkeys]::SendWait('+{Prtsc}')
                \$img = [Windows.Forms.Clipboard]::GetImage()
                \$img.Save(\\\"C:\\NamanyayG\\Work\\omnilens\\screenshot.jpg\\\", [Drawing.Imaging.ImageFormat]::Jpeg)\"
        """)

    def perform_ocr(self, screenshot_path):
        # Send the screenshot to OpenAI for OCR
        api_key = os.getenv('OPENAI_API_KEY')

        with open(screenshot_path, 'rb') as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
            headers = {
              "Content-Type": "application/json",
              "Authorization": f"Bearer {api_key}"
            }
            payload = {
              "model": "gpt-4-turbo",
              "messages": [
                {
                  "role": "user",
                  "content": [
                    {
                      "type": "text",
                      "text": "Give a summary of what's in the image after 'SUMMARY:' and give full OCR exactly and correctly without any missing details after 'OCR:'"
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
            return response.json()['choices'][0]['message']['content']
        return None

    def start_vapi(self, screen_data):
        assistant_overrides = {
            "variableValues": {
                "screendata": screen_data
            }
        }
        self.vapi.start(assistant_id=VAPI_ASSISTANT_ID, assistant_overrides=assistant_overrides)

    def take_screenshot_and_ocr(self):
        print("Starting!")
        self.update_state('loading')
        screenshot = self.take_and_save_screenshot()
        screenshot_path = './screenshot.jpg'
        screen_data = self.perform_ocr(screenshot_path)
        # screen_data = "Hello, world!"
        self.update_state('talking')
        self.start_vapi(screen_data)
        # Print the OCR result
        print(screen_data)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = MainWindow()
    sys.exit(app.exec_())

