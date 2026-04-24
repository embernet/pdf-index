import fitz
import re
# import numpy as np # Implicitly used by wordcloud, but we avoid direct use to prevent conflicts if possible
from collections import Counter
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage, QColor
from wordcloud import WordCloud, STOPWORDS
import traceback

EXTRA_STOPWORDS = {
    "http", "https",
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "mon", "tue", "wed", "thu", "fri", "sat", "sun",
}

def recolor_wordcloud(wc, existing_keywords):
    """Recolor a cached WordCloud without changing layout. Returns (QImage, layout_data)."""
    keyword_set = {k.lower() for k in existing_keywords}

    def color_func(word, font_size, position, orientation, random_state=None, **kwargs):
        if word.lower() in keyword_set:
            return "green"
        return "black"

    wc.recolor(color_func=color_func)
    return generate_cloud_image(wc)


def generate_cloud_image(wc):
    """Convert a WordCloud to (QImage, layout_data). Shared helper."""
    from PIL import ImageFont, ImageDraw, Image

    pil_img = wc.to_image()
    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")

    data = pil_img.tobytes("raw", "RGB")
    q_img = QImage(data, pil_img.width, pil_img.height, QImage.Format.Format_RGB888)
    q_img = q_img.copy()  # Detach from local buffer

    font_path = wc.font_path
    layout_data = []

    for item in wc.layout_:
        word_or_tuple, size, position, orientation, color = item
        if isinstance(word_or_tuple, tuple):
            word = word_or_tuple[0]
        else:
            word = word_or_tuple
        y, x = position

        font = ImageFont.truetype(font_path, int(size))
        dummy_img = Image.new('RGB', (1, 1))
        draw = ImageDraw.Draw(dummy_img)
        bbox = draw.textbbox((x, y), word, font=font, anchor="lt")
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]

        layout_data.append({
            "word": word,
            "rect": (x, y, w, h),
            "orientation": orientation
        })

    return q_img, layout_data


class TagCloudThread(QThread):
    finished = pyqtSignal(object, list, object) # QImage, layout list, WordCloud obj
    error = pyqtSignal(str)
    
    def __init__(self, pdf_path, existing_keywords, custom_stopwords=None):
        super().__init__()
        self.pdf_path = pdf_path
        self.existing_keywords = {k.lower() for k in existing_keywords}
        self.custom_stopwords = custom_stopwords or set()

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
                stopwords=STOPWORDS | EXTRA_STOPWORDS | self.custom_stopwords,
                min_font_size=10,
                max_font_size=100,
                prefer_horizontal=0.9
            )
            
            wc.generate(full_text)

            q_img, layout_data = generate_cloud_image(wc)
            self.finished.emit(q_img, layout_data, wc)
            
        except Exception as e:
            traceback.print_exc()
            self.error.emit(str(e))


class IndexCloudThread(QThread):
    """Generate a word cloud from index results, sized by page count."""
    finished = pyqtSignal(object, list)  # QImage, layout list
    error = pyqtSignal(str)

    def __init__(self, raw_results):
        super().__init__()
        # raw_results: {term: [(page_idx, label), ...]}
        self.raw_results = raw_results

    def run(self):
        try:
            # Build frequency dict: term → number of pages
            frequencies = {}
            for term, pages in self.raw_results.items():
                if pages:
                    frequencies[term] = len(pages)

            if not frequencies:
                self.error.emit("No index entries to display.")
                return

            wc = WordCloud(
                width=800,
                height=600,
                background_color="white",
                min_font_size=10,
                max_font_size=100,
                prefer_horizontal=0.9,
                color_func=lambda *args, **kwargs: "black",
            )

            wc.generate_from_frequencies(frequencies)

            q_img, layout_data = generate_cloud_image(wc)
            self.finished.emit(q_img, layout_data)

        except Exception as e:
            traceback.print_exc()
            self.error.emit(str(e))


class NotInIndexCloudThread(QThread):
    """Generate a word cloud from PDF words that are NOT in the index."""
    finished = pyqtSignal(object, list)  # QImage, layout list
    error = pyqtSignal(str)

    def __init__(self, pdf_path, indexed_terms, custom_stopwords=None):
        super().__init__()
        self.pdf_path = pdf_path
        # Split each indexed term into its component words and use as stopwords
        extra = set()
        for term in indexed_terms:
            for word in re.split(r'\W+', term.lower()):
                if word:
                    extra.add(word)
        self.indexed_stopwords = extra
        self.custom_stopwords = custom_stopwords or set()

    def run(self):
        try:
            doc = fitz.open(self.pdf_path)
            full_text = ""
            for page in doc:
                full_text += page.get_text("text") + " "
            doc.close()

            wc = WordCloud(
                width=800,
                height=600,
                background_color="white",
                stopwords=STOPWORDS | EXTRA_STOPWORDS | self.custom_stopwords | self.indexed_stopwords,
                min_font_size=10,
                max_font_size=100,
                prefer_horizontal=0.9,
                color_func=lambda *args, **kwargs: "black",
            )
            wc.generate(full_text)
            q_img, layout_data = generate_cloud_image(wc)
            self.finished.emit(q_img, layout_data)

        except Exception as e:
            traceback.print_exc()
            self.error.emit(str(e))
