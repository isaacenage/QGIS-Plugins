"""
LLM OCR Dialog for extracting bearing-distance data from TCT images.
Uses LLM Vision APIs (Gemini, OpenAI, etc.) for OCR and structured parsing.
"""

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QTextEdit, QLineEdit, QApplication,
    QProgressDialog, QComboBox, QWidget
)
from qgis.PyQt.QtGui import QPixmap, QImage, QDesktopServices
from qgis.PyQt.QtCore import Qt, QBuffer, QIODevice, QSettings, QUrl, QThread, pyqtSignal, QTimer
from .. import theme
import os
import re
import json
import base64
import urllib.request
import urllib.error
import urllib.parse
import time

try:
    from .tie_point_selector_dialog import _TIEPOINT_DF  # Import tie point data
except ImportError:
    _TIEPOINT_DF = None

# Load the UI file
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 'forms', 'TCT_OCR_Dialog.ui'))


def open_https_request(request, timeout):
    """Open a urllib request, permitting only the https scheme.

    urllib.request.urlopen would also follow file:// or other custom
    schemes; every LLM API endpoint this dialog talks to is https, so
    anything else is rejected before a connection is attempted.
    """
    scheme = urllib.parse.urlparse(request.full_url).scheme.lower()
    if scheme != "https":
        raise ValueError(
            f"Refusing to open URL with scheme '{scheme}'; only https is allowed.")
    return urllib.request.urlopen(request, timeout=timeout)  # nosec B310 - scheme validated as https above


class ApiCallWorker(QThread):
    """Worker thread for making API calls without blocking the UI."""

    # Signals
    finished = pyqtSignal(str)  # Emits the LLM response text
    error = pyqtSignal(str)  # Emits error message

    def __init__(self, dialog, api_key, prompt):
        super().__init__()
        self.dialog = dialog
        self.api_key = api_key
        self.prompt = prompt

    def run(self):
        """Execute the API call in a separate thread."""
        try:
            llm_response = self.dialog.call_llm_api(self.api_key, self.prompt)
            if llm_response:
                self.finished.emit(llm_response)
            else:
                self.error.emit(f"Failed to get response from {self.dialog.current_provider}.")
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg:
                error_msg += "\n\nPlease check your API Key."
            self.error.emit(f"Failed to process image: {error_msg}")


class ApiKeyHelpDialog(QDialog):
    """Dialog showing instructions to get an API key based on provider."""

    # Provider configuration for help dialog
    PROVIDERS = {
        "Gemini": {
            "title": "Get Your Free Gemini API Key",
            "url": "https://aistudio.google.com/app/apikey",
            "instructions": (
                "<ol style='margin-left: 15px;'>"
                "<li style='margin-bottom: 8px;'>Click the <b>'Open Google AI Studio'</b> button below.</li>"
                "<li style='margin-bottom: 8px;'>Sign in with your Google account.</li>"
                "<li style='margin-bottom: 8px;'>Click <b>'Get API key'</b> on the top left of the page.</li>"
                "<li style='margin-bottom: 8px;'>Click <b>'Create API key'</b>.</li>"
                "<li style='margin-bottom: 8px;'>Copy the generated key string.</li>"
                "</ol>"
            )
        },
        "OpenAI": {
            "title": "Get Your OpenAI API Key",
            "url": "https://platform.openai.com/api-keys",
            "instructions": (
                "<ol style='margin-left: 15px;'>"
                "<li style='margin-bottom: 8px;'>Click the <b>'Open OpenAI Platform'</b> button below.</li>"
                "<li style='margin-bottom: 8px;'>Sign in or create an account.</li>"
                "<li style='margin-bottom: 8px;'>Click <b>'Create new secret key'</b>.</li>"
                "<li style='margin-bottom: 8px;'>Name your key and click 'Create secret key'.</li>"
                "<li style='margin-bottom: 8px;'>Copy the key immediately (you won't see it again).</li>"
                "</ol>"
            )
        },
        "DeepSeek": {
            "title": "Get Your DeepSeek API Key",
            "url": "https://platform.deepseek.com/api_keys",
            "instructions": (
                "<ol style='margin-left: 15px;'>"
                "<li style='margin-bottom: 8px;'>Click the <b>'Open DeepSeek Platform'</b> button below.</li>"
                "<li style='margin-bottom: 8px;'>Sign in or create an account.</li>"
                "<li style='margin-bottom: 8px;'>Navigate to the <b>API Keys</b> section.</li>"
                "<li style='margin-bottom: 8px;'>Create a new API key.</li>"
                "</ol>"
            )
        }
    }

    def __init__(self, parent=None, provider="Gemini"):
        super().__init__(parent)
        self.provider = provider if provider in self.PROVIDERS else "Gemini"
        config = self.PROVIDERS[self.provider]

        self.target_url = config['url']

        self.setWindowTitle(f"How to Get a {self.provider} API Key")
        self.setMinimumWidth(450)
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(15)

        # Instructions
        html_content = (
            f"<h3>{config['title']}</h3>"
            f"<p>To use the OCR feature with {self.provider}, you need a valid API key.</p>"
            f"{config['instructions']}"
            "<li style='margin-bottom: 8px; margin-left: 15px;'>"
            "Return to this plugin and paste it into the <b>'API Key'</b> field.</li>"
            "<br>"
        )

        label = QLabel(html_content)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(True)
        self.layout.addWidget(label)

        # Action Buttons
        btn_box = QHBoxLayout()

        # Styled 'Open' button
        self.open_url_btn = QPushButton(f"Open {self.provider} Console")
        self.open_url_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_url_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self.open_url_btn.clicked.connect(self.open_url)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)

        btn_box.addWidget(self.open_url_btn)
        btn_box.addStretch()
        btn_box.addWidget(self.close_btn)

        self.layout.addLayout(btn_box)

    def open_url(self):
        """Open the API key URL in the default browser."""
        url = QUrl(self.target_url)
        QDesktopServices.openUrl(url)


class LLMOCRDialog(QDialog, FORM_CLASS):
    """Dialog for extracting bearing-distance data from TCT images using various LLM APIs."""

    # Provider Configuration
    PROVIDER_CONFIG = {
        "Gemini": {
            "api_url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent",
            "model": "gemini-3-flash-preview",  # Free tier with vision support
            "style": "gemini"
        },
        "OpenAI": {
            "api_url": "https://api.openai.com/v1/chat/completions",
            "model": "gpt-4o-mini",  # Cost effective
            "style": "openai"
        },
        "DeepSeek": {
            "api_url": "https://api.deepseek.com/chat/completions",
            "model": "deepseek-chat",  # Only supported endpoint
            "style": "openai"
        }
    }

    # Maximum image dimension to reduce token usage (smaller = fewer tokens)
    # Increased to 2048 to ensure text legibility for full pages
    MAX_IMAGE_DIMENSION = 2048

    def __init__(self, parent=None):
        """Constructor."""
        super(LLMOCRDialog, self).__init__(parent)
        self.setupUi(self)

        # Apply the shared Title Plotter theme (neutral chrome + teal accent)
        theme.apply(self)

        # Store the parent dialog reference
        self.parent_dialog = parent

        # Initialize image data
        self.current_image_base64 = None
        self.current_image_mime = None
        self.current_qimage = None

        # Store parsed data for later use (when Done is clicked)
        self.parsed_property_info = None

        # Load settings
        self.settings = QSettings('TitlePlotterPH', 'GeminiOCR')

        # Load saved provider (default to Gemini)
        self.current_provider = self.settings.value('provider', 'Gemini')
        if self.current_provider not in self.PROVIDER_CONFIG:
            self.current_provider = 'Gemini'

        # Connect signals
        self.uploadButton.clicked.connect(self.upload_image)
        self.pasteButton.clicked.connect(self.paste_from_clipboard)
        self.doneButton.clicked.connect(self.accept_and_apply)
        self.cancelButton.clicked.connect(self.reject)

        # Add API key input field
        self.setup_api_key_input()

        # --- Middle Section (Image + Text) ---
        mid_layout = QHBoxLayout()

        # Create a container for the image preview and Parse button
        image_container = QWidget()
        image_layout = QVBoxLayout(image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(5)

        # Move imagePreview from vertical layout to this new container
        self.verticalLayout.removeWidget(self.imagePreview)
        image_layout.addWidget(self.imagePreview, 1)

        # Add Parse button at the bottom right of image container
        parse_btn_layout = QHBoxLayout()
        parse_btn_layout.addStretch()
        self.parseButton = QPushButton("Parse")
        self.parseButton.setToolTip("Parse the image using AI to extract bearing data")
        self.parseButton.setFixedWidth(80)
        self.parseButton.clicked.connect(self.process_image)
        parse_btn_layout.addWidget(self.parseButton)
        image_layout.addLayout(parse_btn_layout)

        mid_layout.addWidget(image_container, 2)  # Wider column

        # Create a container for the LLM response text
        response_container = QWidget()
        response_layout = QVBoxLayout(response_container)
        response_layout.setContentsMargins(0, 0, 0, 0)
        response_layout.setSpacing(5)

        # Add QTextEdit for LLM response
        self.rawOcrTextEdit = QTextEdit(self)
        self.rawOcrTextEdit.setReadOnly(False)  # Allow editing for manual corrections
        self.rawOcrTextEdit.setPlaceholderText("Extracted text will appear here. You may edit it manually.")
        response_layout.addWidget(self.rawOcrTextEdit, 1)

        mid_layout.addWidget(response_container, 1)  # Narrower column

        # Insert the middle layout after the API key section (index 1)
        # Note: Index 0 is API key (inserted), Index 1 was Image (removed), Index 2 is buttons
        # So inserting at 1 puts it between API key and buttons
        self.verticalLayout.insertLayout(1, mid_layout)

        # Update window title
        self.update_window_title()

    def update_window_title(self):
        self.setWindowTitle(f"TCT Image OCR ({self.current_provider})")

    def setup_api_key_input(self):
        """Add provider selection and API key input field."""
        # Main layout for top section
        top_layout = QVBoxLayout()
        top_layout.setSpacing(10)

        # --- Provider Selection ---
        provider_layout = QHBoxLayout()
        provider_label = QLabel("AI Provider:")
        provider_label.setFixedWidth(80)

        self.providerCombo = QComboBox()
        self.providerCombo.addItems(self.PROVIDER_CONFIG.keys())
        self.providerCombo.setCurrentText(self.current_provider)
        self.providerCombo.currentIndexChanged.connect(self.on_provider_changed)

        provider_layout.addWidget(provider_label)
        provider_layout.addWidget(self.providerCombo)
        top_layout.addLayout(provider_layout)

        # --- API Key Input ---
        api_key_layout = QHBoxLayout()

        api_key_label = QLabel("API Key:")
        api_key_label.setFixedWidth(80)

        self.apiKeyInput = QLineEdit()
        self.apiKeyInput.setEchoMode(QLineEdit.EchoMode.Password)
        self.apiKeyInput.setPlaceholderText(f"Enter your {self.current_provider} API key")

        # Load saved API key for current provider
        saved_key = self.settings.value(f'api_key_{self.current_provider}', '')
        if saved_key:
            self.apiKeyInput.setText(saved_key)

        # Add show/hide toggle button
        self.toggleKeyBtn = QPushButton("Show")
        self.toggleKeyBtn.setFixedWidth(70)
        self.toggleKeyBtn.clicked.connect(self.toggle_api_key_visibility)

        # Add 'Get Key' help button
        self.helpBtn = QPushButton("Get API Key")
        self.helpBtn.setToolTip("Click for instructions on how to get a free API key")
        self.helpBtn.clicked.connect(self.show_api_help)

        # Style the help button to look like a link or action
        self.helpBtn.setStyleSheet(
            "color: #14575b; font-weight: bold; text-decoration: underline; "
            "background: transparent; border: none;")
        self.helpBtn.setCursor(Qt.CursorShape.PointingHandCursor)

        api_key_layout.addWidget(api_key_label)
        api_key_layout.addWidget(self.apiKeyInput)
        api_key_layout.addWidget(self.toggleKeyBtn)
        api_key_layout.addWidget(self.helpBtn)

        top_layout.addLayout(api_key_layout)

        # Insert at the top of the dialog
        self.verticalLayout.insertLayout(0, top_layout)

    def on_provider_changed(self):
        """Handle provider change."""
        new_provider = self.providerCombo.currentText()

        # Save key for previous provider
        old_key = self.apiKeyInput.text().strip()
        if old_key:
            self.settings.setValue(f'api_key_{self.current_provider}', old_key)

        # Update current provider
        self.current_provider = new_provider
        self.settings.setValue('provider', self.current_provider)

        # Update UI text
        self.apiKeyInput.setPlaceholderText(f"Enter your {self.current_provider} API key")
        self.update_window_title()

        # Load key for new provider
        saved_key = self.settings.value(f'api_key_{self.current_provider}', '')
        self.apiKeyInput.setText(saved_key)

    def toggle_api_key_visibility(self):
        """Toggle API key visibility."""
        if self.apiKeyInput.echoMode() == QLineEdit.EchoMode.Password:
            self.apiKeyInput.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggleKeyBtn.setText("Hide")
        else:
            self.apiKeyInput.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggleKeyBtn.setText("Show")

    def show_api_help(self):
        """Show the dialog with instructions on getting an API key."""
        dialog = ApiKeyHelpDialog(self, provider=self.current_provider)
        dialog.exec()

    def upload_image(self):
        """Handle image upload from file."""
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Select TCT Image",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)"
        )

        if file_name:
            self.load_image_from_file(file_name)

    def paste_from_clipboard(self):
        """Handle image paste from clipboard."""
        clipboard = QApplication.clipboard()
        image = clipboard.image()

        if not image.isNull():
            # Resize if too large to reduce token usage
            image = self.resize_image_if_needed(image)
            self.current_qimage = image
            # Convert QImage to base64 for LLM API
            self.current_image_base64, self.current_image_mime = self.qimage_to_base64(image)
            self.display_image(image)
        else:
            QMessageBox.warning(self, "Error", "No image found in clipboard.")

    def resize_image_if_needed(self, qimage):
        """Resize image if it exceeds maximum dimensions to reduce API token usage."""
        width = qimage.width()
        height = qimage.height()
        max_dim = self.MAX_IMAGE_DIMENSION

        if width > max_dim or height > max_dim:
            # Scale down while maintaining aspect ratio
            if width > height:
                new_width = max_dim
                new_height = int(height * max_dim / width)
            else:
                new_height = max_dim
                new_width = int(width * max_dim / height)

            print(f"Resizing image from {width}x{height} to {new_width}x{new_height}")
            return qimage.scaled(
                new_width, new_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)

        return qimage

    def load_image_from_file(self, file_path):
        """Load, resize if needed, and display image from file."""
        try:
            # Load image using QImage
            qimage = QImage(file_path)
            if qimage.isNull():
                raise Exception("Failed to load image file")

            # Resize if too large to reduce token usage
            qimage = self.resize_image_if_needed(qimage)
            self.current_qimage = qimage

            # Convert to base64 for LLM API
            self.current_image_base64, self.current_image_mime = self.qimage_to_base64(qimage)

            # Display image
            self.display_image(qimage)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image: {str(e)}")

    def qimage_to_base64(self, qimage):
        """Convert QImage to base64 string using JPEG for smaller file size."""
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        # Use JPEG with 70% quality - good enough for OCR, much smaller size
        qimage.save(buffer, "JPEG", 70)
        image_data = bytes(buffer.data())
        base64_str = base64.b64encode(image_data).decode('utf-8')
        print(f"Image encoded: {len(base64_str) // 1024} KB base64")
        return base64_str, 'image/jpeg'

    def display_image(self, image):
        """Display image in the preview area."""
        pixmap = QPixmap.fromImage(image)
        scaled_pixmap = pixmap.scaled(
            self.imagePreview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.imagePreview.setPixmap(scaled_pixmap)

    def extract_json_from_response(self, response):
        """Extract JSON from LLM response, handling various formats.

        Handles:
        - Plain JSON
        - JSON wrapped in ```json ... ``` code blocks
        - JSON wrapped in ``` ... ``` code blocks
        - JSON with leading/trailing text
        """
        text = response.strip()

        # Method 1: Try to find JSON in markdown code blocks
        # Pattern: ```json\n{...}\n``` or ```\n{...}\n```
        json_block_pattern = re.compile(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', re.IGNORECASE)
        match = json_block_pattern.search(text)
        if match:
            extracted = match.group(1).strip()
            # Verify it looks like JSON (starts with { and ends with })
            if extracted.startswith('{') and extracted.endswith('}'):
                return extracted

        # Method 2: Simple markdown removal
        clean = text
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()
        if clean.startswith('{') and clean.endswith('}'):
            return clean

        # Method 3: Find JSON object using brace matching
        # Find the first { and match to its closing }
        start_idx = text.find('{')
        if start_idx != -1:
            brace_count = 0
            end_idx = start_idx
            for i, char in enumerate(text[start_idx:], start_idx):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i
                        break
            if brace_count == 0:
                extracted = text[start_idx:end_idx + 1]
                return extracted

        # Method 4: Return stripped text as-is (let json.loads fail with good error)
        return text

    def process_image(self):
        """Process the image using LLM Vision API for OCR and structured parsing.

        Sends the image directly to the LLM which performs both OCR and
        structured data extraction in a single call.
        """
        if not self.current_image_base64:
            QMessageBox.warning(self, "Error", "No image to process.")
            return

        # Get API key
        api_key = self.apiKeyInput.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Error", f"Please enter your {self.current_provider} API key.")
            return

        # Save API key
        self.settings.setValue(f'api_key_{self.current_provider}', api_key)

        # Clear previous text
        self.rawOcrTextEdit.clear()

        # Create animated progress dialog (0 to 0 creates a busy indicator)
        self.progress = QProgressDialog(f"Processing image with {self.current_provider}...", "Cancel", 0, 0, self)
        self.progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress.setMinimumDuration(0)
        self.progress.setValue(0)  # Start the animation
        self.progress.show()

        # Create timer to keep progress bar animated and UI responsive
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(lambda: QApplication.processEvents())
        self.progress_timer.start(100)  # Update every 100ms

        print(f"DEBUG: Sending image to {self.current_provider} for OCR and parsing...")
        print(f"DEBUG: API Key starts with: '{api_key[:4]}...'")

        try:
            # Create prompt for vision-based OCR and parsing
            # This prompt is designed to handle various Philippine land title formats
            prompt = """You are an expert OCR system for Philippine land titles (TCT/OCT).

TASK: Extract ALL information from this land title image including property details and technical description.

PROPERTY INFORMATION TO EXTRACT:
1. Registered Owner - Full name(s) of the owner(s)
2. Lot Number - The lot number (e.g., "Lot 1", "Lot 1-A")
3. Survey Number - Survey identification (e.g., "Psd-04-123456", "LRC Psd-12345")
4. Property Location - Full address/location (Barangay, Municipality/City, Province)
5. Lot Area - Total area in square meters

TECHNICAL DESCRIPTION FORMATS TO RECOGNIZE:
1. Line labels: "1-2", "2-3", "Corner 1", "Line 1", "TP-1", "thence", or just sequential lines
2. Bearings: "N 78 32 W", "N. 78° 32' W.", "N78-32-W", "North 78 deg 32 min West"
3. Distances: "936.15 M", "936.15m", "936.15 meters", "936.15"

EXTRACTION RULES:
- Extract EVERY bearing-distance pair in the order they appear
- Bearing format: Direction (N/S) + Degrees + Minutes + Quadrant (E/W)
- Distance is always in meters (ignore unit labels)
- Some titles show seconds (e.g., N 45 30 15 E) - ignore seconds, use only degrees and minutes
- If a line says "thence" it means continue to next bearing

OUTPUT FORMAT - Return STRICT JSON with this exact schema:
{
    "property_info": {
        "registered_owner": "Full name of owner(s) or null if not visible",
        "lot_number": "Lot number or null",
        "survey_number": "Survey number (Psd, LRC, etc.) or null",
        "property_location": "Full location/address or null",
        "lot_area": "Area in sq.m. as number (e.g., 500.00) or null"
    },
    "tie_point": {
        "name": "BLLM No. 1, MBM, BLCM, or similar monument name (or null)",
        "province": "province name if visible (or null)",
        "municipality": "municipality/city name if visible (or null)"
    },
    "technical_description": [
        {
            "line": "original line label (e.g., 1-2, TP-1)",
            "direction": "N or S",
            "degrees": 78,
            "minutes": 32,
            "quadrant": "E or W",
            "distance": 936.15
        }
    ]
}

CRITICAL:
- Output ONLY valid JSON, no markdown code blocks
- Extract ALL bearing lines, not just the first few. If the list is long, continue until the end. DO NOT TRUNCATE.
- Preserve the exact order of lines as they appear in the document
- Extract property information even if technical description is not visible"""

            # Create and start worker thread
            self.worker = ApiCallWorker(self, api_key, prompt)
            self.worker.finished.connect(self.on_api_success)
            self.worker.error.connect(self.on_api_error)
            self.worker.start()

            # Handle cancel button
            self.progress.canceled.connect(self.on_api_canceled)

        except Exception as e:
            self.progress.close()
            error_msg = str(e)
            if "401" in error_msg:
                error_msg += "\n\nPlease check your API Key."
            QMessageBox.critical(self, "Error", f"Failed to process image: {error_msg}")

    def on_api_canceled(self):
        """Handle when user cancels the progress dialog."""
        if hasattr(self, 'progress_timer'):
            self.progress_timer.stop()
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()

    def on_api_error(self, error_msg):
        """Handle API call errors."""
        if hasattr(self, 'progress_timer'):
            self.progress_timer.stop()
        self.progress.close()
        QMessageBox.critical(self, "Error", error_msg)

    def on_api_success(self, llm_response):
        """Handle successful API response."""
        if hasattr(self, 'progress_timer'):
            self.progress_timer.stop()
        self.progress.close()

        # Process the response
        print(f"DEBUG: Raw LLM response:\n{llm_response[:1000]}...")

        # Extract JSON from response using multiple methods
        clean_text = self.extract_json_from_response(llm_response)
        print(f"DEBUG: Cleaned text:\n{clean_text[:500]}...")

        try:
            data = json.loads(clean_text)

            # Store property info for later use when Done is clicked
            self.parsed_property_info = data.get('property_info', {})

            # Build human-readable display text
            display_lines = []

            # 1. Display Property Information
            property_info = data.get('property_info', {})
            if property_info:
                display_lines.append("=== PROPERTY INFORMATION ===")
                if property_info.get('registered_owner'):
                    display_lines.append(f"Registered Owner: {property_info['registered_owner']}")
                if property_info.get('lot_number'):
                    display_lines.append(f"Lot Number: {property_info['lot_number']}")
                if property_info.get('survey_number'):
                    display_lines.append(f"Survey Number: {property_info['survey_number']}")
                if property_info.get('property_location'):
                    display_lines.append(f"Property Location: {property_info['property_location']}")
                if property_info.get('lot_area'):
                    display_lines.append(f"Lot Area: {property_info['lot_area']} sq.m.")
                display_lines.append("")

            # 2. Display Tie Point
            tie_point_info = data.get('tie_point', {})
            if tie_point_info and tie_point_info.get('name'):
                display_lines.append("=== TIE POINT ===")
                display_lines.append(f"Monument: {tie_point_info.get('name', 'N/A')}")
                if tie_point_info.get('municipality'):
                    display_lines.append(f"Municipality: {tie_point_info['municipality']}")
                if tie_point_info.get('province'):
                    display_lines.append(f"Province: {tie_point_info['province']}")
                display_lines.append("")

            # 3. Display Technical Description
            bearings = data.get('technical_description', [])
            if bearings:
                display_lines.append("=== TECHNICAL DESCRIPTION ===")
                for i, b in enumerate(bearings):
                    line_label = b.get('line', f'{i + 1}')
                    direction = b.get('direction', '?')
                    degrees = b.get('degrees', 0)
                    minutes = b.get('minutes', 0)
                    quadrant = b.get('quadrant', '?')
                    distance = b.get('distance', 0)
                    display_lines.append(f"{line_label}: {direction} {degrees} {minutes} {quadrant}, {distance} M")

            # Set the display text
            self.rawOcrTextEdit.setPlainText('\n'.join(display_lines) if display_lines else clean_text)

            # Process and apply data
            messages = []

            # Handle Tie Point lookup
            if tie_point_info:
                found_tp = self.lookup_tie_point(tie_point_info)
                if found_tp:
                    self.parent_dialog.tie_point = found_tp
                    self.parent_dialog.tiePointNorthingInput.setText(str(found_tp['northing']))
                    self.parent_dialog.tiePointEastingInput.setText(str(found_tp['easting']))
                    messages.append(f"Tie Point found: {found_tp['name']}")
                elif tie_point_info.get('name'):
                    messages.append(f"Tie Point identified ({tie_point_info.get('name')}) but not found in database.")

            # Summary message
            if property_info:
                prop_count = sum(1 for v in property_info.values() if v)
                if prop_count > 0:
                    messages.append(f"Extracted {prop_count} property field(s).")

            if bearings:
                messages.append(f"Extracted {len(bearings)} bearing lines.")
                messages.append("Click 'Done' to apply to Technical Description.")

                if messages:
                    QMessageBox.information(self, "Parse Complete", "\n".join(messages))
            else:
                if messages:
                    messages.append("No technical description found.")
                    QMessageBox.information(self, "Parse Complete", "\n".join(messages))
                else:
                    QMessageBox.warning(self, "Warning", "No data could be extracted from the image.")

        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON response from LLM: {e}")
            print(f"Attempted to parse: {clean_text[:200]}...")

            # Fallback to legacy parsing on the raw LLM response
            bearings = self.parse_bearings_legacy(llm_response)
            if bearings:
                # Format the extracted bearings for display
                lines = []
                for i, b in enumerate(bearings):
                    lines.append(
                        f"{i + 1}: {b['direction']} {b['degrees']} "
                        f"{b['minutes']} {b['quadrant']}, {b['distance']} M")
                self.rawOcrTextEdit.setPlainText('\n'.join(lines))

                QMessageBox.information(
                    self, "Parse Complete",
                    f"LLM response format was unexpected.\n"
                    f"Used fallback parser and found {len(bearings)} bearing lines.\n"
                    f"Click 'Done' to apply to Technical Description."
                )
            else:
                # Display detailed error info for debugging
                error_info = (
                    f"JSON Parse Error: {str(e)}\n\n"
                    f"--- Raw LLM Response ---\n{llm_response}\n\n"
                    f"--- Cleaned Text ---\n{clean_text}"
                )
                self.rawOcrTextEdit.setPlainText(error_info)
                QMessageBox.warning(
                    self, "Parsing Failed",
                    f"Could not parse the LLM response.\n"
                    f"Error: {str(e)}\n\n"
                    "The raw response is displayed for debugging."
                )

    def lookup_tie_point(self, info):
        """Look up tie point in the loaded dataframe."""
        if _TIEPOINT_DF is None or _TIEPOINT_DF.empty:
            return None

        # Handle None values from JSON null - use 'or' to convert None to empty string
        name = (info.get('name') or '').replace(" ", "").lower()
        province = (info.get('province') or '').lower()
        municipality = (info.get('municipality') or '').lower()

        if not name:
            return None

        # Create a copy for searching
        df = _TIEPOINT_DF.copy()
        df["__name"] = df["Tie Point Name"].astype(str).str.replace(" ", "").str.lower()

        # Filter by name first (most specific)
        matches = df[df["__name"].str.contains(name, na=False)]

        if matches.empty:
            return None

        # Try to narrow down by location if multiple matches
        if len(matches) > 1 and (province or municipality):
            if province:
                matches_prov = matches[matches["Province"].str.lower().str.contains(province, na=False)]
                if not matches_prov.empty:
                    matches = matches_prov

            if municipality and len(matches) > 1:
                matches_muni = matches[matches["Municipality"].str.lower().str.contains(municipality, na=False)]
                if not matches_muni.empty:
                    matches = matches_muni

        if not matches.empty:
            # Take the first best match
            row = matches.iloc[0]
            return {
                'name': row["Tie Point Name"],
                'description': row["Description"],
                'province': row["Province"],
                'municipality': row["Municipality"],
                'northing': float(row["Northing"]),
                'easting': float(row["Easting"])
            }
        return None

    def call_llm_api(self, api_key, prompt):
        """Dispatch call to appropriate API handler (with image)."""
        config = self.PROVIDER_CONFIG[self.current_provider]

        if config["style"] == "gemini":
            return self.call_gemini_native_api(api_key, prompt, config["api_url"])
        else:
            return self.call_openai_style_api(api_key, prompt, config)

    def call_gemini_native_api(self, api_key, prompt, api_url, retry_count=0):
        """Call Gemini Native API."""
        try:
            url = f"{api_url}?key={api_key}"

            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": self.current_image_mime,
                                "data": self.current_image_base64
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "maxOutputTokens": 8192,
                    "temperature": 0
                }
            }

            headers = {"Content-Type": "application/json"}
            data = json.dumps(payload).encode('utf-8')
            request = urllib.request.Request(url, data=data, headers=headers, method='POST')

            print("Sending request to Gemini...")
            with open_https_request(request, timeout=120) as response:
                result = json.loads(response.read().decode('utf-8'))

                if 'candidates' in result and len(result['candidates']) > 0:
                    candidate = result['candidates'][0]
                    if 'content' in candidate and 'parts' in candidate['content']:
                        parts = candidate['content']['parts']
                        if len(parts) > 0 and 'text' in parts[0]:
                            return parts[0]['text']
                return None

        except urllib.error.HTTPError as e:
            # Re-use existing error handling logic
            return self.handle_http_error(e, api_key, prompt, "gemini", retry_count)
        except Exception as e:
            raise e

    def call_openai_style_api(self, api_key, prompt, config, retry_count=0):
        """Call OpenAI-compatible API (OpenAI, DeepSeek)."""
        try:
            url = config["api_url"]
            model = config["model"]

            # Construct standard OpenAI vision payload
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{self.current_image_mime};base64,{self.current_image_base64}"
                            }
                        }
                    ]
                }
            ]

            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0,
                "max_tokens": 2048
            }

            # Headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            data = json.dumps(payload).encode('utf-8')
            request = urllib.request.Request(url, data=data, headers=headers, method='POST')

            print(f"Sending request to {self.current_provider}...")
            # Longer timeout for vision analysis
            with open_https_request(request, timeout=120) as response:
                result = json.loads(response.read().decode('utf-8'))

                if 'choices' in result and len(result['choices']) > 0:
                    return result['choices'][0]['message']['content']
                return None

        except urllib.error.HTTPError as e:
            return self.handle_http_error(e, api_key, prompt, "openai", retry_count)
        except Exception as e:
            raise e

    def handle_http_error(self, e, api_key, prompt, style, retry_count):
        """Centralized HTTP error handling with retry logic."""
        error_body = e.read().decode('utf-8') if e.fp else ''
        code = e.code
        print(f"HTTP Error {code}: {error_body}")

        if code == 429 and retry_count < 2:
            wait_time = self.extract_retry_time(error_body)
            if wait_time and wait_time <= 120:
                reply = QMessageBox.question(self, "Rate Limited",
                                             f"API rate limit reached. Wait {int(wait_time)} seconds and retry?",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    QApplication.processEvents()
                    time.sleep(wait_time + 1)
                    if style == "gemini":
                        return self.call_gemini_native_api(
                            api_key, prompt,
                            self.PROVIDER_CONFIG[self.current_provider]['api_url'],
                            retry_count + 1)
                    else:  # "openai" style
                        return self.call_openai_style_api(
                            api_key, prompt,
                            self.PROVIDER_CONFIG[self.current_provider],
                            retry_count + 1)

        self.show_api_error(code, error_body)
        return None

    def extract_retry_time(self, error_body):
        """Extract retry wait time from error message."""
        try:
            match = re.search(r'retry in (\d+(?:\.\d+)?)', error_body, re.IGNORECASE)
            if match:
                return float(match.group(1))
        except Exception:
            pass
        return 60

    def show_api_error(self, code, error_body):
        """Show appropriate error message based on HTTP error code."""
        try:
            error_json = json.loads(error_body)
            error_message = error_json.get('error', {}).get('message', error_body)
        except Exception:
            error_message = error_body

        if code == 400:
            QMessageBox.critical(self, "API Error",
                                 f"Bad request.\n\nDetails: {error_message}")
        elif code == 401 or code == 403:
            QMessageBox.critical(self, "API Error",
                                 f"Invalid or unauthorized API key.\n\nDetails: {error_message}")
        elif code == 429:
            QMessageBox.critical(self, "API Error",
                                 f"Rate limit or quota exceeded.\n\nDetails: {error_message}\n\n"
                                 "Please wait a moment or check your API quota at:\n"
                                 "https://console.cloud.google.com/apis/api/generativelanguage.googleapis.com/quotas")
        elif code == 404:
            QMessageBox.critical(self, "API Error",
                                 f"Model not found. Try a different model.\n\nDetails: {error_message}")
        else:
            QMessageBox.critical(self, "API Error",
                                 f"HTTP Error {code}:\n\n{error_message}")

    def parse_bearings_legacy(self, raw_text):
        """Legacy text parser as fallback - handles various formats including partial JSON."""
        bearings = []

        # Log the raw text for debugging
        print("Legacy parser input:", raw_text[:500])

        # Method 1: Try to extract from JSON-like structure (for when JSON parse fails but data is there)
        # Look for patterns like "direction": "N", "degrees": 45, etc.
        json_bearing_pattern = re.compile(
            r'"direction"\s*:\s*"([NS])"\s*,\s*'
            r'"degrees"\s*:\s*(\d+)\s*,\s*'
            r'"minutes"\s*:\s*(\d+)\s*,\s*'
            r'"quadrant"\s*:\s*"([EW])"\s*,\s*'
            r'"distance"\s*:\s*([\d.]+)',
            re.IGNORECASE
        )
        json_matches = json_bearing_pattern.findall(raw_text)
        if json_matches:
            print(f"Found {len(json_matches)} bearings from JSON-like structure")
            for match in json_matches:
                try:
                    bearings.append({
                        'direction': match[0].upper(),
                        'degrees': int(match[1]),
                        'minutes': int(match[2]),
                        'quadrant': match[3].upper(),
                        'distance': float(match[4])
                    })
                except (ValueError, IndexError):
                    continue
            if bearings:
                return bearings

        # Method 2: Standard bearing pattern
        # Pattern to match bearing lines like: N 45 30 E 25.50 or N45 30 E 25.50 or N 45° 30' E 25.50m
        bearing_pattern = re.compile(
            r"""
            ([NS])[\s.-]*                        # N or S (with optional separators)
            (\d{1,2})[\s°.-]*                    # Degrees
            (\d{1,2})[\s'''-]*                   # Minutes
            ([EW])[\s,.-]*                       # E or W
            (\d+(?:[.,]\d+)?)\s*[mM]?            # Distance
            """,
            re.IGNORECASE | re.VERBOSE
        )

        # Find all matches
        matches = bearing_pattern.findall(raw_text)

        print(f"Found {len(matches)} bearing-distance matches from text pattern.")

        for match in matches:
            try:
                direction = match[0].upper()
                degrees = int(match[1])
                minutes = int(match[2])
                quadrant = match[3].upper()
                distance = float(match[4].replace(',', '.'))

                # Validate values
                if direction in ['N', 'S'] and quadrant in ['E', 'W']:
                    if 0 <= degrees <= 90 and 0 <= minutes <= 59 and distance > 0:
                        bearing = {
                            'direction': direction,
                            'degrees': degrees,
                            'minutes': minutes,
                            'quadrant': quadrant,
                            'distance': distance
                        }
                        bearings.append(bearing)
                        print(f"Valid bearing: {direction} {degrees}° {minutes}' {quadrant} {distance}m")
                    else:
                        print(f"Invalid values: deg={degrees}, min={minutes}, dist={distance}")
                else:
                    print(f"Invalid direction/quadrant: {direction}/{quadrant}")

            except (ValueError, IndexError) as e:
                print(f"Error processing match {match}: {str(e)}")
                continue

        return bearings

    def add_bearings_to_parent(self, bearings):
        """Add extracted bearings to the parent dialog's bearing rows.

        If existing rows have data, append new bearings after them instead of overwriting.
        """
        if not self.parent_dialog:
            return

        if not bearings:
            return

        # Helper function to check if a row has data
        def row_has_data(row):
            return (row.directionInput.text().strip() or
                    row.degreesInput.text().strip() or
                    row.minutesInput.text().strip() or
                    row.quadrantInput.text().strip() or
                    row.distanceInput.text().strip())

        # Find the first empty row index
        first_empty_idx = None
        for idx, row in enumerate(self.parent_dialog.bearing_rows):
            if not row_has_data(row):
                first_empty_idx = idx
                break

        # If all existing rows have data, we'll append after the last row
        if first_empty_idx is None:
            first_empty_idx = len(self.parent_dialog.bearing_rows)

        # Fill existing empty rows first
        bearing_idx = 0
        for row_idx in range(first_empty_idx, len(self.parent_dialog.bearing_rows)):
            if bearing_idx >= len(bearings):
                break
            row = self.parent_dialog.bearing_rows[row_idx]
            bearing = bearings[bearing_idx]
            row.directionInput.setText(bearing['direction'])
            row.degreesInput.setText(str(bearing['degrees']))
            row.minutesInput.setText(str(bearing['minutes']))
            row.quadrantInput.setText(bearing['quadrant'])
            row.distanceInput.setText(str(bearing['distance']))
            bearing_idx += 1

        # Add new rows for remaining bearings
        while bearing_idx < len(bearings):
            self.parent_dialog.add_bearing_row()
            row = self.parent_dialog.bearing_rows[-1]
            bearing = bearings[bearing_idx]
            row.directionInput.setText(bearing['direction'])
            row.degreesInput.setText(str(bearing['degrees']))
            row.minutesInput.setText(str(bearing['minutes']))
            row.quadrantInput.setText(bearing['quadrant'])
            row.distanceInput.setText(str(bearing['distance']))
            bearing_idx += 1

        # Update preview
        self.parent_dialog.generate_wkt()

    def apply_text_to_parent(self):
        """Parse the text from the response box and apply bearings and property info to the parent dialog.

        Returns True if data was successfully applied, False otherwise.
        """
        if not self.parent_dialog:
            QMessageBox.warning(self, "Error", "No parent dialog available.")
            return False

        text = self.rawOcrTextEdit.toPlainText().strip()
        applied_something = False

        # Apply stored property info (from when image was parsed)
        if self.parsed_property_info:
            self.apply_property_info_to_parent(self.parsed_property_info)
            applied_something = True

        if not text:
            # No text to apply - return whether we applied property info
            return applied_something

        bearings = []

        # First, try to parse as JSON
        try:
            # Try to extract JSON from the text
            clean_text = self.extract_json_from_response(text)
            data = json.loads(clean_text)

            # Handle tie point if present
            tie_point_info = data.get('tie_point', {})
            if tie_point_info:
                found_tp = self.lookup_tie_point(tie_point_info)
                if found_tp:
                    self.parent_dialog.tie_point = found_tp
                    self.parent_dialog.tiePointNorthingInput.setText(str(found_tp['northing']))
                    self.parent_dialog.tiePointEastingInput.setText(str(found_tp['easting']))

            # Apply property info from JSON if not already applied from stored data
            if not self.parsed_property_info:
                property_info = data.get('property_info', {})
                if property_info:
                    self.apply_property_info_to_parent(property_info)
                    applied_something = True

            # Extract bearings from JSON
            bearings = data.get('technical_description', [])
        except (json.JSONDecodeError, KeyError):
            # If JSON parsing fails, try to parse as plain text
            bearings = self.parse_text_bearings(text)

        if not bearings:
            # Try legacy parsing as last resort
            bearings = self.parse_bearings_legacy(text)

        if bearings:
            self.add_bearings_to_parent(bearings)
            applied_something = True

        return applied_something

    def apply_property_info_to_parent(self, property_info):
        """Apply extracted property information to the parent dialog's input fields."""
        if not self.parent_dialog or not property_info:
            return

        # Registered Owner
        if property_info.get('registered_owner'):
            self.parent_dialog.registeredOwnerInput.setText(str(property_info['registered_owner']))

        # Lot Number
        if property_info.get('lot_number'):
            self.parent_dialog.lotNumberInput.setText(str(property_info['lot_number']))

        # Survey Number
        if property_info.get('survey_number'):
            self.parent_dialog.surveyNumberInput.setText(str(property_info['survey_number']))

        # Lot Area / Title Area
        if property_info.get('lot_area'):
            area_value = property_info['lot_area']
            # Format as string with sq.m. if it's a number
            if isinstance(area_value, (int, float)):
                self.parent_dialog.titleAreaInput.setText(f"{area_value} sq.m.")
            else:
                self.parent_dialog.titleAreaInput.setText(str(area_value))

        # Property Location - try to parse into barangay, municipality, province
        if property_info.get('property_location'):
            self.parse_and_apply_location(property_info['property_location'])

        # Expand the Property Information panel so user can see the filled data
        if hasattr(self.parent_dialog, 'property_info_content'):
            self.parent_dialog.property_info_content.setVisible(True)
            if hasattr(self.parent_dialog, 'property_info_toggle_arrow'):
                self.parent_dialog.property_info_toggle_arrow.setText("▲")

    def parse_and_apply_location(self, location_str):
        """Parse a location string and apply to barangay, municipality, province fields.

        Handles formats like:
        - "Barangay X, Municipality Y, Province Z"
        - "Brgy. X, City of Y, Z"
        - "X, Y, Z" (assumes order: barangay, municipality, province)
        """
        if not location_str or not self.parent_dialog:
            return

        location_str = str(location_str).strip()

        # Split by comma
        parts = [p.strip() for p in location_str.split(',') if p.strip()]

        if len(parts) >= 3:
            # Assume: barangay, municipality, province
            self.parent_dialog.barangayInput.setText(parts[0])
            self.parent_dialog.municipalityInput.setText(parts[1])
            self.parent_dialog.provinceInput.setText(parts[2])
        elif len(parts) == 2:
            # Assume: municipality, province (no barangay)
            self.parent_dialog.municipalityInput.setText(parts[0])
            self.parent_dialog.provinceInput.setText(parts[1])
        elif len(parts) == 1:
            # Just put the whole thing in municipality
            self.parent_dialog.municipalityInput.setText(parts[0])
        else:
            # Fallback: put whole string in municipality
            self.parent_dialog.municipalityInput.setText(location_str)

    def accept_and_apply(self):
        """Apply any extracted bearings and close the dialog."""
        # Try to apply text if available (silently - no error if empty)
        self.apply_text_to_parent()
        # Close the dialog
        self.accept()

    def parse_text_bearings(self, text):
        """Parse bearing data from plain text format.

        Expected formats:
        - "1-2: N 45 30 E, 125.50"
        - "TP-1: S 78 32 W, 936.15 M"
        - "N 45 30 E 125.50"
        """
        bearings = []
        lines = text.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Pattern to match bearing lines with or without line labels
            # Handles: "1-2: N 45 30 E, 125.50" or "N 45 30 E 125.50"
            pattern = re.compile(
                r"""
                (?:[\w\-]+\s*:\s*)?          # Optional line label (e.g., "1-2:", "TP-1:")
                ([NS])\s*                     # Direction N or S
                (\d{1,2})\s*[°]?\s*           # Degrees
                (\d{1,2})\s*[''']?\s*         # Minutes
                ([EW])\s*                     # Quadrant E or W
                [,\s]*                        # Separator (comma or space)
                ([\d.]+)\s*[mM]?              # Distance
                """,
                re.IGNORECASE | re.VERBOSE
            )

            match = pattern.search(line)
            if match:
                try:
                    bearing = {
                        'direction': match.group(1).upper(),
                        'degrees': int(match.group(2)),
                        'minutes': int(match.group(3)),
                        'quadrant': match.group(4).upper(),
                        'distance': float(match.group(5).replace(',', '.'))
                    }

                    # Validate values
                    if (bearing['direction'] in ['N', 'S'] and
                        bearing['quadrant'] in ['E', 'W'] and
                        0 <= bearing['degrees'] <= 90 and
                        0 <= bearing['minutes'] <= 59 and
                            bearing['distance'] > 0):
                        bearings.append(bearing)
                except (ValueError, IndexError):
                    continue

        return bearings

    def resizeEvent(self, event):
        """Handles resize event for the dialog."""
        super().resizeEvent(event)
        if self.rawOcrTextEdit.isVisible():
            self.rawOcrTextEdit.updateGeometry()
