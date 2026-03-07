import fitz
import re
# import numpy as np # Implicitly used by wordcloud, but we avoid direct use to prevent conflicts if possible
from collections import Counter
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage, QColor
from wordcloud import WordCloud, STOPWORDS
import traceback

class TagCloudThread(QThread):
    finished = pyqtSignal(object, list) # QImage, layout list
    error = pyqtSignal(str)
    
    def __init__(self, pdf_path, existing_keywords):
        super().__init__()
        self.pdf_path = pdf_path
        self.existing_keywords = {k.lower() for k in existing_keywords}

    def run(self):
        try:
            doc = fitz.open(self.pdf_path)
            full_text = ""
            for page in doc:
                full_text += page.get_text("text") + " "
            doc.close()
            
            # Custom Color Function
            def color_func(word, font_size, position, orientation, random_state=None, **kwargs):
                if word.lower() in self.existing_keywords:
                    return "green"
                return "black"

            wc = WordCloud(
                width=800, 
                height=600, 
                background_color="white",
                color_func=color_func,
                stopwords=STOPWORDS,
                min_font_size=10,
                max_font_size=100,
                prefer_horizontal=0.9
            )
            
            wc.generate(full_text)
            
            # Convert to QImage using PIL (avoids numpy asarray issues in some environments)
            pil_img = wc.to_image()
            
            # Ensure RGB
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")
                
            data = pil_img.tobytes("raw", "RGB")
            
            q_img = QImage(data, pil_img.width, pil_img.height, QImage.Format.Format_RGB888)
            q_img = q_img.copy() # Detach from local buffer
            
            # Extract Layout for Click Detection
            font_path = wc.font_path
            from PIL import ImageFont, ImageDraw, Image
            
            layout_data = []
            
            for item in wc.layout_:
                # layout_ item: (word, size, position=(y,x), orientation, color)
                word, size, position, orientation, color = item
                y, x = position
                
                # Re-calculate bounding box
                font = ImageFont.truetype(font_path, int(size))
                
                # Dummy draw
                dummy_img = Image.new('RGB', (1, 1))
                draw = ImageDraw.Draw(dummy_img)
                
                bbox = draw.textbbox((x, y), word, font=font, anchor="lt")
                # (left, top, right, bottom)
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                
                layout_data.append({
                    "word": word,
                    "rect": (x, y, w, h), # x,y is top-left
                    "orientation": orientation
                })

            self.finished.emit(q_img, layout_data)
            
        except Exception as e:
            traceback.print_exc()
            self.error.emit(str(e))
