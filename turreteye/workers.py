# -*- coding: utf-8 -*-
import io

from PyQt6.QtCore import QThread, pyqtSignal
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdfcanvas
from tqdm import tqdm

# --- Workers ---
class PdfExportWorker(QThread):
    finished = pyqtSignal(str) # Emits message on finish

    def __init__(self, image_list, save_path, opener_func):
        super().__init__()
        self.image_list = image_list
        self.save_path = save_path
        self.opener_func = opener_func

    def run(self):
        try:
            c = pdfcanvas.Canvas(self.save_path, pagesize=A4)
            pw, ph = A4
            for fpath in tqdm(self.image_list):
                try:
                    img = self.opener_func(fpath).convert("RGB")
                    iw, ih = img.size
                    scale = min(pw/iw, ph/ih)
                    nw, nh = iw*scale, ih*scale
                    with io.BytesIO() as bio:
                        img.save(bio, format="PNG")
                        bio.seek(0)
                        c.drawImage(ImageReader(bio), (pw-nw)/2, (ph-nh)/2, nw, nh)
                        c.showPage()
                except: pass
            c.save()
            self.finished.emit("SUCCESS")
        except Exception as e:
            self.finished.emit(f"ERROR||{str(e)}")
