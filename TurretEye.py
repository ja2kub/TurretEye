# turreteye.py — pełny kod z panelem pomocy (F1) i obsługą .ico + Easter Egg: Turret Mode (Ctrl+P)
# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import tkinter.font as tkFont
from tkinterdnd2 import TkinterDnD
from PIL import Image, ImageTk, ImageEnhance, ImageFilter, ImageOps, ImageChops, ImageDraw, ImageFont
import os
import sys
import pickle
import customtkinter as ctk
import rawpy
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
import threading
from tqdm import tqdm
import io
import time
import traceback
import requests
import math
import ctypes
from threading import Timer

class TurretEyeApp:
    _RAW_EXT = (".cr2", ".nef", ".arw", ".dng")
    _THUMB_SIZE = (148, 148)
    _THUMB_INNER = (140, 140)

    def __init__(self, root):
        self.root = root
        self.root.title("TurretEye")
        self.root.geometry("1200x800")
        self.root.minsize(800, 600)

        try:
            if hasattr(sys, "_MEIPASS"):  
                # gdy działa jako exe (PyInstaller spakował pliki)
                icon_path = os.path.join(sys._MEIPASS, "TurretEye.ico")
            else:
                # gdy uruchamiasz z .py
                icon_path = os.path.join(os.path.dirname(__file__), "TurretEye.ico")

            # ustawienie ikony dla customtkinter
            self.root.iconbitmap(icon_path)
        except Exception as e:
            print("Nie udało się ustawić ikony:", e)

        # theme defaults
        self.theme = "dark"
        self.bg = "#1c1c1c"
        self.fg = "#ffffff"
        self.btn_bg = "#2a2a2a"
        self.hover_bg = "#3c3c3c"

        self.root.configure(bg=self.bg)

        # image state
        self.image_list = []
        self.current_image_index = 0
        self.zoom_factor = 1.0
        self.rotation = 0
        self.loaded_folder = None
        self.fullscreen = False
        self.original_image = None        # PIL.Image original (before adjustments)
        self.displayed_image = None       # PIL.Image currently shown (after adjustments)
        self.last_loaded_path = None

        # adjustments
        self.brightness = 1.0
        self.saturation = 1.0
        self.sharpness = 1.0
        self._adjustment_timer = None
        self._last_displayed_image = None

        # history
        self.history = []
        self.future = []

        # slideshow
        self.slideshow_active = False
        self.slideshow_thread = None

        # slideshow mode flag: enable fade only in slideshow
        self._slideshow_mode = False

        # thumbnails cache (path -> PIL.Image thumbnail)
        self.thumb_cache = {}

        self._img_size_cache = {}
        # pan state
        self._panning = False
        self._pan_start = (0, 0)

        # fade-in state
        self._fade_steps = 6
        self._fade_duration = 0.15  # seconds (subtelny)
        self._fade_lock = threading.Lock()

        # [FIX] znacznik, by po załadowaniu obraz trafił w centrum
        self._should_center = False  # [FIX]

        # canvas
        self.canvas = tk.Canvas(root, highlightthickness=0)
        self.canvas.configure(bg=self.bg)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-3>", self.show_context_menu)
        # enable drag & drop
        try:
            self.canvas.drop_target_register('*')
            self.canvas.dnd_bind('<<Drop>>', self.drop_file)
        except Exception:
            pass

        # mouse interactions
        # Windows: event.delta, Linux: Button-4/5 — handle both
        self.canvas.bind("<MouseWheel>", self.on_mousewheel_zoom)
        self.canvas.bind("<Button-4>", self.on_mousewheel_zoom)
        self.canvas.bind("<Button-5>", self.on_mousewheel_zoom)
        self.canvas.bind("<ButtonPress-1>", self.start_pan)
        self.canvas.bind("<B1-Motion>", self.do_pan)
        self.canvas.bind("<ButtonRelease-1>", self.end_pan)

        # >>> NEW: double-click toggle fit <-> 100%
        self.canvas.bind("<Double-Button-1>", self.toggle_zoom_mode)

        # status and controls
        self.status_label = tk.Label(root, text="", anchor="w", relief=tk.FLAT, bg=self.bg, fg=self.fg)
        self.status_label.pack(fill=tk.X, side=tk.BOTTOM)

        self.control_frame = tk.Frame(root, bg=self.bg)
        self.control_frame.pack(side=tk.BOTTOM, pady=10)

        # >>> NEW: small overlay counter "12/84" in the top-right corner
        self.counter_var = tk.StringVar(value="")
        self.counter_label = tk.Label(
            self.canvas,
            textvariable=self.counter_var,
            font=("Segoe UI", 11, "bold"),
            bg=self.btn_bg,
            fg=self.fg
        )
        # anchor to top-right corner of canvas with slight padding
        self.counter_label.place(relx=1.0, x=-10, y=10, anchor="ne")

        self.buttons = []
        self.create_buttons()
        self.bind_keys()
        self.load_last_session()

        self.root.bind("<Configure>", self.on_resize)
        # set CTk theme
        try:
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("dark-blue")
        except:
            pass
        # ensure style conformity
        self.toggle_theme(initial=True)

        # >>> NEW (Turret Mode) state
        self.turret_mode = False
        self._turret = {
            "base": None,
            "barrel": None,
            "bubble_items": [],
            "bubble_text": None,
            "pedestal": None,
            "radius": 18,
            "margin": 16
        }
        self._last_mouse = (0, 0)

        # Initialize navigation fields
        self._nav_init_fields()

        # Bindings for extra features
        self.root.bind("<Control-b>", self._dc_open_palette_window)
        self.root.bind("<Control-t>", self._nav_open_window)

    # ---------------- UI: buttons & keys ----------------
    def create_buttons(self):
        # Ikonki / etykiety prostsze — możesz je zmienić
        global prev_icon, next_icon, zoom_in_icon, zoom_out_icon, rotate_left_icon, rotate_right_icon, fullscreen_icon, theme_icon
        prev_icon = "◀"
        next_icon = "▶"
        zoom_in_icon = "+"
        zoom_out_icon = "-"
        rotate_left_icon = "↺"
        rotate_right_icon = "↻"
        fullscreen_icon = "⛶"
        theme_icon = "☼"

        def create_btn(icon, command):
            btn = tk.Label(self.control_frame, text=icon, font=("Segoe UI", 12, "bold"),
                           width=6, height=2, bd=0, relief=tk.FLAT, cursor="hand2", bg=self.btn_bg, fg=self.fg)
            btn.pack(side=tk.LEFT, padx=4)
            btn.bind("<Button-1>", lambda e: command())
            btn.bind("<Enter>", lambda e: btn.configure(bg=self.hover_bg))
            btn.bind("<Leave>", lambda e: btn.configure(bg=self.btn_bg))
            self.buttons.append(btn)

        create_btn(prev_icon, self.show_prev_image)
        create_btn(next_icon, self.show_next_image)
        create_btn(zoom_in_icon, self.zoom_in)
        create_btn(zoom_out_icon, self.zoom_out)
        create_btn(rotate_left_icon, self.rotate_left)
        create_btn(rotate_right_icon, self.rotate_right)
        create_btn(fullscreen_icon, self.toggle_fullscreen)
        create_btn(theme_icon, self.toggle_theme)
        create_btn("Plik", self.select_file)
        create_btn("Folder", self.select_folder)
        create_btn("Zapisz", self.save_image_as)
        create_btn("Edycja", self.open_edit_panel)

    def bind_keys(self):
        self.root.bind("<Left>", lambda event: self.show_prev_image())
        self.root.bind("<Right>", lambda event: self.show_next_image())
        self.root.bind("<plus>", lambda event: self.zoom_in())
        self.root.bind("<minus>", lambda event: self.zoom_out())
        self.root.bind("<f>", lambda event: self.toggle_fullscreen())
        self.root.bind("<r>", lambda event: self.rotate_right())
        self.root.bind("<l>", lambda event: self.rotate_left())
        self.root.bind("<Control-u>", lambda event: self.load_image_from_url())
        self.root.bind("<Alt-p>", lambda event: self.export_to_pdf())
        self.root.bind("<Alt-i>", lambda event: self.export_folder_to_pdf())
        self.root.bind("<F10>", lambda event: self.toggle_slideshow())
        self.root.bind("<Control-z>", lambda event: self.undo_edit())
        self.root.bind("<Control-y>", lambda event: self.redo_edit())
        self.root.bind("<Control-l>", lambda event: self.mirror_image())

        # szybkie filtry Ctrl+1..5
        self.root.bind("<Control-1>", lambda e: self.apply_style("sketch"))
        self.root.bind("<Control-2>", lambda e: self.apply_style("sepia"))
        self.root.bind("<Control-3>", lambda e: self.apply_style("oil"))
        self.root.bind("<Control-4>", lambda e: self.apply_style("contrast"))
        self.root.bind("<Control-5>", lambda e: self.apply_style("bw"))

        # Panel pomocy (ładna tabelka skrótów)
        self.root.bind("<F1>", lambda e: self.open_help_panel())

        # >>> NEW: Easter Egg — Turret Mode toggle
        self.root.bind("<Control-p>", lambda e: self.toggle_turret_mode())

    # ---------------- Drag & drop ----------------
    def drop_file(self, event):
        # event.data contains path(s), may be wrapped in {}
        try:
            data = event.data
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            filepath = data.strip().replace('{', '').replace('}', '')
            # if multiple paths, take first
            if ' ' in filepath and os.path.exists(filepath.split(' ')[0]):
                filepath = filepath.split(' ')[0]
            if os.path.isfile(filepath):
                ext = os.path.splitext(filepath)[1].lower()
                if ext in [".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".jfif", ".svg", ".cr2", ".nef", ".arw", ".dng", ".ico"]:
                    self.loaded_folder = None
                    self.image_list = [filepath]
                    self.current_image_index = 0
                    self.load_image(filepath)
        except Exception as e:
            print("Drop error:", e)

    # ---------------- helpers: ICO handling ----------------
    def _open_image_with_ico_support(self, path):
        """
        Otwiera obraz z obsługą plików ICO (wybiera największą klatkę).
        Zwraca PIL.Image (RGBA).
        """
        ext = os.path.splitext(path)[1].lower()
        if ext == ".ico":
            im = Image.open(path)
            # Wybierz największą ramkę (size)
            max_size = (0, 0)
            best = None
            try:
                n = getattr(im, "n_frames", 1)
            except Exception:
                n = 1
            for i in range(n):
                try:
                    im.seek(i)
                    if im.size[0] * im.size[1] > max_size[0] * max_size[1]:
                        max_size = im.size
                        best = im.copy()
                except Exception:
                    pass
            if best is None:
                best = im.copy()
            return best.convert("RGBA")
        elif ext == ".svg":
            try:
                import cairosvg
            except Exception as e:
                raise RuntimeError("Do obsługi .svg wymagany jest pakiet 'cairosvg'. Zainstaluj: pip install cairosvg")
            try:
                with open(path, 'rb') as f:
                    svg_bytes = f.read()
                png_bytes = cairosvg.svg2png(bytestring=svg_bytes)
                return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
            except Exception as e:
                raise RuntimeError(f"Błąd konwersji SVG: {e}")
        else:
            # standardowe formaty
            return Image.open(path).convert("RGBA")

    # ---------------- Loading images ----------------
    def load_image(self, path):
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext in [".cr2", ".nef", ".arw", ".dng"]:
                with rawpy.imread(path) as raw:
                    rgb = raw.postprocess()
                    img = Image.fromarray(rgb).convert("RGBA")
            else:
                img = self._open_image_with_ico_support(path)

            # apply saved session state for this image if present
            self.original_image = img.copy()
            self.displayed_image = img.copy()
            self.last_loaded_path = path
            # reset rotation/zoom unless session file says otherwise (handled in load_last_session)
            self.rotation = 0
            self.zoom_factor = 1.0
            self.push_history(img)
            self.update_status_bar(path, img)
            self._center_canvas()  # [FIX] ustaw centrowanie po załadowaniu
            # Display with fade only in slideshow mode; otherwise immediate
            if getattr(self, '_slideshow_mode', False):
                self._display_with_fade(img)
            else:
                self.display_image_from(img)
            # >>> NEW: update overlay counter
            self._update_counter_overlay()

            # Nav updates
            self._nav_update_highlight()
            self._nav_scroll_to_index(self.current_image_index)
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się załadować obrazu:\n{e}")

    # -------------- history ----------------
    def push_history(self, img):
        if img:
            try:
                self.history.append(img.copy())
                if len(self.history) > 30:
                    self.history.pop(0)
                self.future.clear()
            except Exception:
                pass

    def undo_edit(self):
        if len(self.history) > 1:
            last = self.history.pop()
            self.future.append(last)
            self.displayed_image = self.history[-1].copy()
            self.original_image = self.history[-1].copy()
            self._display_with_fade(self.displayed_image)

    def redo_edit(self):
        if self.future:
            img = self.future.pop()
            self.history.append(img.copy())
            self.displayed_image = img
            self.original_image = img
            # Display with fade only in slideshow mode; otherwise immediate
            if getattr(self, '_slideshow_mode', False):
                self._display_with_fade(img)
            else:
                self.display_image_from(img)

    
    def _slideshow_next(self):
        """Advance to the next image with fade (only in slideshow mode)."""
        if not self.image_list:
            return
        # ensure slideshow fade is active
        self._slideshow_mode = True
        if self.current_image_index < len(self.image_list) - 1:
            self.current_image_index += 1
        else:
            self.current_image_index = 0
        self._update_counter_overlay()
        self.display_image()
        self.save_last_session()

# -------------- slideshow ----------------
    def toggle_slideshow(self):
        # Start/stop fullscreen slideshow with 5s interval, Esc to exit, and fade-in only in this mode
        if self.slideshow_active:
            # stop slideshow
            self.slideshow_active = False
            self._slideshow_mode = False
            try:
                self.root.unbind("<Escape>")
            except Exception:
                pass
            try:
                self.root.attributes("-fullscreen", False)
            except Exception:
                pass
            return

        if not self.image_list:
            return

        # start slideshow
        self.slideshow_active = True
        self._slideshow_mode = True
        try:
            self.root.attributes("-fullscreen", True)
        except Exception:
            pass
        # allow exiting with Esc
        self.root.bind("<Escape>", lambda e: self.toggle_slideshow())

        def run_slideshow():
            while self.slideshow_active:
                # show next slide with fade
                try:
                    self.root.after(0, self._slideshow_next)
                except Exception:
                    pass
                # wait ~5 seconds (50 * 0.1s)
                for _ in range(50):
                    if not self.slideshow_active:
                        return
                    time.sleep(0.1)

        self.slideshow_thread = threading.Thread(target=run_slideshow, daemon=True)
        self.slideshow_thread.start()


    # ---------------- PDF export (folder) ----------------
    def export_folder_to_pdf(self):
        if not self.loaded_folder or not self.image_list:
            messagebox.showwarning("Brak folderu", "Najpierw wybierz folder z obrazami.")
            return
        filepath = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not filepath:
            return

        # progress window
        progress_win = tk.Toplevel(self.root)
        progress_win.title("Eksport do PDF...")
        progress_win.geometry("420x80")
        progress_win.attributes("-topmost", True)
        tk.Label(progress_win, text="Trwa eksport...").pack(pady=(8, 4))
        pb = ttk.Progressbar(progress_win, orient="horizontal", length=360, mode="determinate")
        pb.pack(padx=10, pady=(0, 10))
        num_images = len(self.image_list)
        pb["maximum"] = num_images

        def run_export():
            try:
                pdf = pdfcanvas.Canvas(filepath, pagesize=A4)
                for i, path in enumerate(self.image_list):
                    pb["value"] = i + 1
                    progress_win.update()

                    ext = os.path.splitext(path)[1].lower()
                    if ext in [".cr2", ".nef", ".arw", ".dng"]:
                        with rawpy.imread(path) as raw:
                            rgb = raw.postprocess()
                            img = Image.fromarray(rgb).convert("RGB")
                    else:
                        img = self._open_image_with_ico_support(path).convert("RGB")

                    img_width, img_height = img.size
                    # choose orientation
                    if img_width > img_height:
                        page_size = A4[::-1]
                    else:
                        page_size = A4

                    page_w, page_h = page_size
                    margin = 40
                    max_w = page_w - 2 * margin
                    max_h = page_h - 2 * margin
                    scale = min(max_w / img_width, max_h / img_height)

                    new_w = img_width * scale
                    new_h = img_height * scale
                    x = (page_w - new_w) / 2
                    y = (page_h - new_h) / 2

                    # save temp to memory (avoid many IO ops)
                    with io.BytesIO() as bio:
                        img.save(bio, format="PNG")
                        bio.seek(0)
                        image_reader = ImageReader(bio) 
                        pdf.setPageSize(page_size)
                        pdf.drawImage(image_reader, x, y, width=new_w, height=new_h)
                        pdf.showPage()
                pdf.save()
                progress_win.destroy()
                messagebox.showinfo("Gotowe", f"Zapisano folder do PDF:\n{filepath}")
            except Exception as e:
                try:
                    progress_win.destroy()
                except:
                    pass
                messagebox.showerror("Błąd PDF", f"Nie udało się zapisać:\n{e}")

        t = threading.Thread(target=run_export, daemon=True)
        t.start()

    # ---------------- select folder/file ----------------
    def select_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.loaded_folder = folder_selected
            supported_exts = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp",
                              ".tif", ".tiff", ".jfif", ".svg",
                              ".cr2", ".nef", ".arw", ".dng", ".ico")
            files = [os.path.join(folder_selected, f) for f in os.listdir(folder_selected)
                     if f.lower().endswith(supported_exts)]
            files.sort()
            self.image_list = files
            self.current_image_index = 0
            self._update_counter_overlay()
            if self.image_list:
                self.rotation = 0
                self.display_image()
                self.save_last_session()

            self._nav_refresh()
            self._nav_scroll_to_index(self.current_image_index)

    # ---------------- display helpers ----------------
    def _center_canvas(self):
        # [FIX] oznacz do wycentrowania i spróbuj po ustabilizowaniu geometrii
        self._should_center = True
        self.root.after_idle(self._maybe_center_image)  # [FIX]

    def _maybe_center_image(self):  # [FIX]
        try:
            if not hasattr(self, "canvas_image") or not self.canvas_image:
                return
            self.canvas.update_idletasks()
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            if cw <= 2 or ch <= 2:
                # Canvas jeszcze nie ma sensownych wymiarów — spróbuj ponownie
                self.root.after(50, self._maybe_center_image)
                return
            cx = cw // 2
            cy = ch // 2
            self.canvas.coords(self.canvas_image, cx, cy)
        finally:
            self._should_center = False

    def display_image_from(self, img):
        """Resize & display the PIL.Image `img` on the canvas respecting zoom and rotation.
        This only updates the displayed image without fade."""
        try:
            # apply rotation non-destructive (on a copy)
            tmp = self.original_image.copy()  # FIX: zawsze skaluj z oryginalnego obrazu
            if getattr(self, 'rotation', 0):
                tmp = tmp.rotate(self.rotation, expand=True)
    
            # ensure canvas geometry is up-to-date
            try:
                self.canvas.update_idletasks()
            except Exception:
                pass
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
    
            # jeśli kanwa jeszcze nie ma sensownego rozmiaru -> spróbuj za chwilę ponownie
            if cw <= 2 or ch <= 2:
                # odłóż rysowanie o 50ms — dzięki temu nie trafi na (0,0)
                try:
                    self.root.after(50, lambda i=img: self.display_image_from(i))
                except Exception:
                    # w wyjątkowym przypadku użyj prostego opóźnienia
                    self.root.after(50, lambda i=img: self.display_image_from(i))
                return
    
            w, h = tmp.size
            # compute available canvas size
            win_w = max(200, cw or getattr(self.root, 'winfo_width', lambda: 800)())
            win_h = max(200, ch or (getattr(self.root, 'winfo_height', lambda: 600)() - 100))
            ratio = min(win_w / w, win_h / h) * getattr(self, 'zoom_factor', 1.0)
            new_size = (max(1, int(w * ratio)), max(1, int(h * ratio)))
    
            tmp = tmp.resize(new_size, getattr(Image, 'LANCZOS', Image.BICUBIC))
            self.displayed_image = tmp
            self.displayed_tk = ImageTk.PhotoImage(tmp)
    
            cx, cy = cw // 2, ch // 2
    
            if getattr(self, 'canvas_image', None) is None:
                self.canvas_image = self.canvas.create_image(cx, cy, image=self.displayed_tk, anchor="center")
            else:
                try:
                    self.canvas.coords(self.canvas_image, cx, cy)
                    self.canvas.itemconfig(self.canvas_image, image=self.displayed_tk)
                except Exception:
                    # fallback na recreate
                    try:
                        self.canvas.delete(getattr(self, 'canvas_image', None))
                    except Exception:
                        pass
                    self.canvas_image = self.canvas.create_image(cx, cy, image=self.displayed_tk, anchor="center")
    
            # optional update status bar if exists
            if hasattr(self, '_update_status_bar'):
                try:
                    self._update_status_bar()
                except Exception:
                    pass
        except Exception as e:
            print("Error in display_image_from:", e)

    def _display_with_fade(self, new_img):
        if not new_img:
            return
    
        # jeśli kanwa jeszcze nie ma sensownego rozmiaru -> spróbuj ponownie chwilę później
        try:
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
        except Exception:
            cw, ch = 0, 0
        if cw <= 2 or ch <= 2:
            try:
                self.root.after(50, lambda ni=new_img: self._display_with_fade(ni))
            except Exception:
                pass
            return
    
        # lock to avoid overlapping fades
        lock = getattr(self, '_fade_lock', None)
        if lock is not None:
            try:
                acquired = lock.acquire(blocking=False)
                if not acquired:
                    return
            except Exception:
                # jeśli lock nie działa — ignorujemy i kontynuujemy (bez dublowania)
                acquired = False
        else:
            acquired = False
    
        try:
            steps = 10
            delay = 30
            old_img = getattr(self, 'displayed_image', None)
            if old_img is None:
                # no existing image — just display new image without fade
                try:
                    self.display_image_from(new_img)
                except Exception:
                    pass
                return
    
            for i in range(steps + 1):
                try:
                    blend = Image.blend(old_img, new_img, i / steps)
                    self.display_image_from(blend)
                    # zamiast self.root.update() używamy after/idle — ale tutaj trzymamy prostotę
                    self.root.update_idletasks()
                    self.root.after(delay)
                except Exception:
                    # w razie problemów przerwij fazę fade i ustaw finalny obraz
                    try:
                        self.display_image_from(new_img)
                    except Exception:
                        pass
                    break
            try:
                self.display_image_from(new_img)
            except Exception:
                pass
        finally:
            if lock is not None and acquired:
                try:
                    lock.release()
                except Exception:
                    pass

    def update_status_bar(self, img_path, img_obj):
        try:
            filename = os.path.basename(img_path)
            w, h = img_obj.size
            file_size = os.path.getsize(img_path) if os.path.exists(img_path) else 0
            size_kb = file_size / 1024
            if size_kb >= 1024:
                size_str = f"{size_kb/1024:.2f} MB"
            else:
                size_str = f"{size_kb:.1f} KB"
            self.status_label.config(text=f"{filename} ({w}×{h}, {size_str})")
        except:
            self.status_label.config(text="")

    # >>> NEW: overlay counter updater
    def _update_counter_overlay(self):

        try:
            # Fast, non-blocking counter update.
            if self.image_list:
                txt = f"{self.current_image_index + 1}/{len(self.image_list)}"
            elif self.displayed_image is not None:
                txt = "1/1"
            else:
                txt = ""
            # Skip if unchanged.
            if getattr(self, "_counter_last", None) != txt:
                self._counter_last = txt
                try:
                    # Instant update via StringVar (no geometry recalculation).
                    self.counter_var.set(txt)
                except Exception:
                    # Fallback: config text directly if StringVar not present for any reason.
                    try:
                        self.counter_label.config(text=txt)
                    except Exception:
                        pass
                # Keep it on top without heavy relayout.
                try:
                    self.counter_label.lift()
                except Exception:
                    pass
        except Exception as e:
            print("update counter error:", e)

    def zoom_in(self):
        self.zoom_factor *= 1.1
        self.display_image_from(self.displayed_image)

    def zoom_out(self):
        self.zoom_factor /= 1.1
        self.display_image_from(self.displayed_image)

    def on_mousewheel_zoom(self, event):
        # Windows: event.delta > 0 scroll up, Linux: Button-4=up, Button-5=down
        if getattr(event, "num", None) == 4 or event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def start_pan(self, event):
        self._panning = True
        self._pan_start = (event.x, event.y)

    def do_pan(self, event):
        if self._panning and hasattr(self, "canvas_image"):
            dx = event.x - self._pan_start[0]
            dy = event.y - self._pan_start[1]
            self.canvas.move(self.canvas_image, dx, dy)
            self._pan_start = (event.x, event.y)

    def end_pan(self, event):
        self._panning = False

    # >>> NEW: double-click toggle between FIT and 100% (pixel-perfect)
    def toggle_zoom_mode(self, event=None):
        """
        display_image_from() używa:
            ratio = min(win_w/w, win_h/h) * self.zoom_factor
        gdzie self.zoom_factor=1.0 oznacza "dopasowanie do okna".
        Aby uzyskać 100% (piksel-w-piksel), ustawiamy:
            self.zoom_factor = 1.0 / base_ratio
        """
        if not self.displayed_image:
            return

        # oblicz rozmiar po rotacji (tak jak w display_image_from)
        tmp = self.displayed_image
        if self.rotation:
            tmp = tmp.rotate(self.rotation, expand=True)

        w, h = tmp.size
        self.canvas.update_idletasks()
        win_w = max(200, self.canvas.winfo_width() or self.root.winfo_width())
        win_h = max(200, (self.canvas.winfo_height() or (self.root.winfo_height() - 100)))
        base_ratio = min(win_w / w, win_h / h)

        # jeśli jesteśmy w trybie FIT (zoom_factor ~ 1.0) -> przełącz na 100%
        # w przeciwnym razie wróć do FIT
        if abs(self.zoom_factor - 1.0) < 1e-3:
            # 100% (1:1)
            if base_ratio > 0:
                self.zoom_factor = 1.0 / base_ratio
        else:
            # FIT
            self.zoom_factor = 1.0

        # wycentruj obraz przy przełączaniu
        self._center_canvas()
        self.display_image_from(self.displayed_image)

    # ---------------- rotation ----------------
    def rotate_left(self):
        self.rotation = (self.rotation - 90) % 360
        self.display_image_from(self.displayed_image)

    def rotate_right(self):
        self.rotation = (self.rotation + 90) % 360
        self.display_image_from(self.displayed_image)

    # ---------------- save image ----------------

    def mirror_image(self):
        """Odbicie lustrzane (poziome) bieżącego obrazu. Skrót: Ctrl+L."""
        if not self.original_image:
            return
        try:
            img = ImageOps.mirror(self.original_image.convert("RGBA"))
            self.original_image = img
            self.displayed_image = img
            # reset zoom to ensure całe odbicie jest widoczne – spójne z apply_style
            self.zoom_factor = 1.0
            self.push_history(img)
            self.display_image_from(img)
        except Exception as e:
            print("Błąd odbicia lustrzanego:", e)

    def save_image_as(self):
        if not self.displayed_image:
            messagebox.showwarning("Brak obrazu", "Brak obrazu do zapisania.")
            return
        filepath = filedialog.asksaveasfilename(defaultextension=".png",
                                                filetypes=[("PNG", "*.png"),
                                                           ("JPEG", "*.jpg"),
                                                           ("BMP", "*.bmp"),
                                                           ("WebP", "*.webp")])
        if filepath:
            try:
                image_to_save = self.displayed_image.copy().convert("RGB")
                image_to_save.save(filepath)
                messagebox.showinfo("Zapisano", f"Obraz zapisany do:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Błąd zapisu", f"Nie udało się zapisać obrazu:\n{e}")

    # ---------------- export single PDF ----------------
    def export_to_pdf(self):
        if not self.displayed_image:
            return
        filepath = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not filepath:
            return
        try:
            img = self.displayed_image.convert("RGB")
            img_width, img_height = img.size
            if img_width > img_height:
                page_size = A4[::-1]
            else:
                page_size = A4
            page_w, page_h = page_size
            margin = 40
            max_w = page_w - 2 * margin
            max_h = page_h - 2 * margin
            scale = min(max_w / img_width, max_h / img_height)
            new_w = img_width * scale
            new_h = img_height * scale
            x = (page_w - new_w) / 2
            y = (page_h - new_h) / 2
            temp_img_path = filepath + "_temp.png"
            img.save(temp_img_path, "PNG")
            pdf = pdfcanvas.Canvas(filepath, pagesize=page_size)
            pdf.drawImage(temp_img_path, x, y, width=new_w, height=new_h)
            pdf.showPage()
            pdf.save()
            os.remove(temp_img_path)
            messagebox.showinfo("Eksport zakończony", f"Obraz zapisany jako PDF:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Błąd PDF", f"Nie udało się zapisać PDF:\n{e}")

    # ---------------- edit panel ----------------
    def open_edit_panel(self):
        top = ctk.CTkToplevel(self.root)
        top.title("Edycja obrazu")
        top.geometry("420x360")
        top.attributes("-topmost", True)
        top.configure(fg_color=self.bg)

        def update_and_apply(value=None):
            def apply():
                self.brightness = brightness_var.get()
                self.saturation = saturation_var.get()
                self.sharpness = sharpness_var.get()
                self.apply_adjustments()
                brightness_value.configure(text=f"{self.brightness:.2f}")
                saturation_value.configure(text=f"{self.saturation:.2f}")
                sharpness_value.configure(text=f"{self.sharpness:.2f}")
            if self._adjustment_timer:
                self._adjustment_timer.cancel()
            self._adjustment_timer = Timer(0.1, apply)
            self._adjustment_timer.start()

        brightness_var = tk.DoubleVar(value=self.brightness)
        saturation_var = tk.DoubleVar(value=self.saturation)
        sharpness_var = tk.DoubleVar(value=self.sharpness)

        brightness_value = []
        saturation_value = []
        sharpness_value = []

        def labeled_slider(label_text, variable, value_label_ref):
            frame = ctk.CTkFrame(top, fg_color=self.bg)
            frame.pack(fill="x", padx=20, pady=10)
            ctk.CTkLabel(frame, text=label_text, text_color=self.fg, font=("Segoe UI", 14)).pack(anchor="w")
            slider_frame = ctk.CTkFrame(frame, fg_color=self.bg)
            slider_frame.pack(fill="x")
            slider_min = 0.2
            slider_max = 3.0
            slider = ctk.CTkSlider(
                slider_frame,
                from_=slider_min,
                to=slider_max,
                variable=variable,
                command=lambda x: update_value(slider, value_label),
                progress_color="#1f6aa5",
                button_color="#3b8ed0"
            )
            slider.pack(side="left", fill="x", expand=True)
            value_label = ctk.CTkLabel(slider_frame, text=f"{variable.get():.2f}", width=40, text_color=self.fg)
            value_label.pack(side="right", padx=5)
            value_label_ref.append(value_label)

            def update_value(slider_widget, label_widget):
                label_widget.configure(text=f"{slider_widget.get():.2f}")
                update_and_apply()

            def on_key(event):
                delta = 0.05
                value = slider.get()
                if event.keysym == "Right":
                    slider.set(min(slider_max, value + delta))
                elif event.keysym == "Left":
                    slider.set(max(slider_min, value - delta))
                update_value(slider, value_label)

            slider.bind("<Key>", on_key)

        labeled_slider("Jasność", brightness_var, brightness_value)
        labeled_slider("Nasycenie", saturation_var, saturation_value)
        labeled_slider("Ostrość", sharpness_var, sharpness_value)

        brightness_value = brightness_value[0]
        saturation_value = saturation_value[0]
        sharpness_value = sharpness_value[0]

    def apply_adjustments(self):
        if not self.original_image:
            return
        try:
            img = self.original_image.convert("RGB")
            if (abs(self.brightness - 1.0) > 0.01 or
                abs(self.saturation - 1.0) > 0.01 or
                abs(self.sharpness - 1.0) > 0.01):
                img = ImageEnhance.Brightness(img).enhance(self.brightness)
                img = ImageEnhance.Color(img).enhance(self.saturation)
                img = ImageEnhance.Sharpness(img).enhance(self.sharpness)
            img = img.convert("RGBA")
            if not self._last_displayed_image or img.tobytes() != self._last_displayed_image:
                self.displayed_image = img
                self._last_displayed_image = img.tobytes()
                self.push_history(img)
                self.display_image_from(img)
        except Exception as e:
            print("Błąd w apply_adjustments:", e)

    def apply_style(self, style_name):
        if not self.original_image:
            return
        img = self.original_image.copy().convert("RGB")
        if style_name == "sketch":
            gray = img.convert("L")
            edges = gray.filter(ImageFilter.FIND_EDGES)
            img = ImageOps.invert(edges).convert("RGBA")
        elif style_name == "oil":
            img = img.filter(ImageFilter.SMOOTH_MORE).filter(ImageFilter.DETAIL)
            img = ImageEnhance.Color(img).enhance(1.5).convert("RGBA")
        elif style_name == "sepia":
            pixels = img.load()
            for y in range(img.height):
                for x in range(img.width):
                    r, g, b = pixels[x, y]
                    tr = int(0.393 * r + 0.769 * g + 0.189 * b)
                    tg = int(0.349 * r + 0.686 * g + 0.168 * b)
                    tb = int(0.272 * r + 0.534 * g + 0.131 * b)
                    pixels[x, y] = (min(tr, 255), min(tg, 255), min(tb, 255))
            img = img.convert("RGBA")
        elif style_name == "contrast":
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.0).convert("RGBA")
        elif style_name == "bw":
            img = img.convert("L").convert("RGBA")
        elif style_name == "original":
            img = self.original_image.convert("RGBA")
            self.brightness = 1.0
            self.saturation = 1.0
            self.sharpness = 1.0
        self.displayed_image = img
        self.original_image = img
        self.zoom_factor = 1.0
        self.push_history(img)
        self.display_image_from(img)

    def show_context_menu(self, event):
        stylizacja_menu = {
            "Szkic": lambda: self.apply_style("sketch"),
            "Obraz olejny": lambda: self.apply_style("oil"),
            "Sepia": lambda: self.apply_style("sepia"),
            "Kontrast": lambda: self.apply_style("contrast"),
            "Czarno-biały": lambda: self.apply_style("bw")
        }
        menu_structure = {
            "Obróć w lewo": self.rotate_left,
            "Obróć w prawo": self.rotate_right,
            "---": None,
            "Pełny ekran": self.toggle_fullscreen,
            "Cofnij": self.undo_edit,
            "Stylizacja AI": stylizacja_menu
        }
        CustomContextMenu(self.root, menu_structure, self.theme, event.x_root, event.y_root)

    def load_image_from_url(self):
        def fetch_and_display():
            url = url_entry.get()
            try:
                response = requests.get(url)
                response.raise_for_status()
                img_data = io.BytesIO(response.content)
                img = Image.open(img_data).convert("RGBA")
                self.original_image = img.copy()
                self.displayed_image = img.copy()
                self.image_list = []
                self.rotation = 0
                self.zoom_factor = 1.0
                self.update_status_bar(url, img)
                self._center_canvas()  # [FIX] URL też od razu na środku
                self.display_image_from(img)
                self.push_history(img)
                # >>> NEW: update overlay counter for URL/single
                self._update_counter_overlay()
                top.destroy()
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie udało się załadować obrazu:\n{e}")
        top = ctk.CTkToplevel(self.root)
        top.title("Wklej URL obrazu")
        top.geometry("460x180")
        top.attributes("-topmost", True)
        top.configure(fg_color=self.bg)
        ctk.CTkLabel(top, text="Wprowadź URL do obrazu:", text_color=self.fg, font=("Segoe UI", 14)).pack(pady=(20, 5))
        url_entry = ctk.CTkEntry(
            top,
            width=400,
            fg_color=self.bg,                # kolor pola = tło motywu
            text_color=self.fg,              # kolor tekstu = kolor motywu
            placeholder_text_color="#888888" # szary placeholder
        )
        url_entry.pack(pady=5)
        url_entry.focus()

        ctk.CTkButton(top, text="Załaduj", command=fetch_and_display, width=140).pack(pady=15)

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.root.attributes("-fullscreen", self.fullscreen)

    def save_last_session(self):
        data = {
            "folder": self.loaded_folder,
            "index": self.current_image_index,
            "zoom": self.zoom_factor,
            "rotation": self.rotation
        }
        with open("last_session.pkl", "wb") as f:
            pickle.dump(data, f)

    def load_last_session(self):
        if os.path.exists("last_session.pkl"):
            try:
                with open("last_session.pkl", "rb") as f:
                    data = pickle.load(f)
                if data.get("folder") and os.path.isdir(data["folder"]):
                    self.loaded_folder = data["folder"]
                    self.image_list = [os.path.join(self.loaded_folder, f)
                                       for f in os.listdir(self.loaded_folder)
                                       if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp",
                                                              ".cr2", ".nef", ".arw", ".dng", ".ico"))]
                    self.current_image_index = data.get("index", 0)
                    self.zoom_factor = data.get("zoom", 1.0)
                    self.rotation = data.get("rotation", 0)
                    if self.image_list:
                        self.display_image()
            except Exception as e:
                print(f"Błąd przy wczytywaniu sesji: {e}")
        if not self.image_list:
            self.select_folder()

    def on_resize(self, event):
        if event.widget == self.root and self.displayed_image:
            self.display_image_from(self.displayed_image)
            # nie wymuszamy centrowania przy każdym resize — tylko gdy jest oczekiwane
        # >>> NEW: keep turret anchored bottom-right
        if event.widget == self.root and getattr(self, "turret_mode", False):
            self._position_turret()
            self._update_turret()

    def display_image(self):
        if not self.image_list:
            return
        path = self.image_list[self.current_image_index]
        self.load_image(path)

    def show_prev_image(self):
        if self.image_list and self.current_image_index > 0:
            self.current_image_index -= 1
            self._update_counter_overlay()
            self.display_image()
            self.save_last_session()

    def show_next_image(self):
        if self.image_list and self.current_image_index < len(self.image_list) - 1:
            self.current_image_index += 1
            self._update_counter_overlay()
            self.display_image()
            self.save_last_session()

    def toggle_theme(self, initial=False):
        self.theme = "light" if (self.theme == "dark" and not initial) else ("dark" if not initial else self.theme)
        self.bg = "#ffffff" if self.theme == "light" else "#1c1c1c"
        self.fg = "#000000" if self.theme == "light" else "#ffffff"
        self.btn_bg = "#f0f0f0" if self.theme == "light" else "#2a2a2a"
        self.hover_bg = "#d0d0d0" if self.theme == "light" else "#3c3c3c"
        self.root.configure(bg=self.bg)
        self.canvas.configure(bg=self.bg)
        self.status_label.configure(bg=self.bg, fg=self.fg)
        self.control_frame.configure(bg=self.bg)
        for btn in self.buttons:
            btn.configure(bg=self.btn_bg, fg=self.fg)
        # >>> NEW: odśwież wygląd licznika (kolory)
        try:
            self.counter_label.configure(bg=self.btn_bg, fg=self.fg)
        except:
            pass
        # >>> NEW: apply theme to turret if active
        if getattr(self, "turret_mode", False):
            self._apply_turret_theme()

        self._dc_palette_apply_theme()
        self._nav_apply_theme()

    def select_file(self):
        file_path = filedialog.askopenfilename(filetypes=[
            ("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.webp;*.tif;*.tiff;*.jfif;*.svg;*.cr2;*.nef;*.arw;*.dng;*.ico")
        ])
        if file_path:
            self.loaded_folder = None
            self.image_list = [file_path]
            self.current_image_index = 0
            self.load_image(file_path)

        self._nav_refresh()
        self._nav_scroll_to_index(self.current_image_index)

    # ---------------- help panel (F1) ----------------
    def open_help_panel(self):
        # Eleganckie, lekkie okno CTk z tabelką skrótów
        top = ctk.CTkToplevel(self.root)
        top.title("Skróty klawiaturowe — pomoc (F1)")
        top.geometry("820x720")
        top.attributes("-topmost", True)
        top.configure(fg_color=self.bg)

        header = ctk.CTkFrame(top, fg_color=self.bg)
        header.pack(fill="x", padx=16, pady=(14, 6))
        ctk.CTkLabel(header, text="Skróty klawiaturowe", font=("Segoe UI", 20, "bold"),
                     text_color=self.fg).pack(side="left")
        ctk.CTkLabel(header, text="TurretEye", font=("Segoe UI", 14),
                     text_color=self.fg).pack(side="right")

        table = ctk.CTkScrollableFrame(top, fg_color=self.bg, height=420)
        table.pack(fill="both", expand=True, padx=16, pady=8)

        # kolumny: Skrót | Akcja
        def add_row(row, col1, col2, header=False):
            pad = (6, 6)
            font_left = ("Segoe UI", 12, "bold") if header else ("Segoe UI", 12)
            font_right = ("Segoe UI", 12, "bold") if header else ("Segoe UI", 12)
            bg_frame = ctk.CTkFrame(table, fg_color=self.bg)
            bg_frame.grid(row=row, column=0, sticky="ew", padx=0, pady=0)
            bg_frame.grid_columnconfigure(0, weight=0, minsize=160)
            bg_frame.grid_columnconfigure(1, weight=1)

            left = ctk.CTkLabel(bg_frame, text=col1, text_color=self.fg, font=font_left, anchor="w")
            right = ctk.CTkLabel(bg_frame, text=col2, text_color=self.fg, font=font_right, anchor="w")
            left.grid(row=0, column=0, sticky="w", padx=(8, 12), pady=pad)
            right.grid(row=0, column=1, sticky="w", padx=(8, 8), pady=pad)

            # delikatny separator
            sep = ctk.CTkFrame(table, fg_color=("#3a3a3a" if self.theme == "dark" else "#d9d9d9"), height=1)
            sep.grid(row=row+1, column=0, sticky="ew", padx=(8, 8), pady=(0, 0))

        rows = [
            ("Skrót", "Akcja"),
            ("← / →", "Poprzedni / następny obraz"),
            ("+ / -", "Powiększ / pomniejsz"),
            ("F", "Pełny ekran (przełącz)"),
            ("R / L", "Obróć w prawo / lewo"),
            ("Ctrl + U", "Wklej URL obrazu"),
            ("Ctrl + B", "Paleta kolorów"),
            ("Ctrl + L", "Odbicie lustrzane"),
            ("Ctrl + T", "Okno nawigacji (miniatury)"),
            ("Alt + P", "Zapis obecnego obrazu do PDF"),
            ("Alt + I", "Eksport całego folderu do PDF"),
            ("F10", "Pokaz slajdów (start/stop)"),
            ("Ctrl + Z / Ctrl + Y", "Cofnij / Ponów"),
            ("Ctrl + P", "Turret Mode (włącz/wyłącz) — wieżyczka śledzi kursor, dymek w < 100 px"),
            ("PPM (prawy przycisk)", "Menu kontekstowe (Stylizacja AI, obrót, pełny ekran)"),
            ("Kółko myszy", "Zoom w / out"),
            ("LPM + przeciąganie", "Panorama (przesuwanie)"),
            ("F1", "Ten panel pomocy")
        ]

        for i, (k, d) in enumerate(rows):
            add_row(i*2, k, d, header=(i == 0))

        footer = ctk.CTkFrame(top, fg_color=self.bg)
        footer.pack(fill="x", padx=16, pady=(8, 14))
        ctk.CTkLabel(footer, text="Podpowiedź: przeciągnij plik obrazu (wspiera także .ico) bezpośrednio na okno.",
                     text_color=self.fg, font=("Segoe UI", 11, "italic")).pack(anchor="w")

    # -------------------- TURret MODE (Easter Egg) --------------------
    def toggle_turret_mode(self):
        self.turret_mode = not self.turret_mode
        if getattr(self, "turret_mode", False):
            self._create_turret_items()
            self._position_turret()
            self._apply_turret_theme()
            # bind motion tracking
            self.canvas.bind("<Motion>", self._on_mouse_move)
            # init aim with last known mouse (center if none)
            if self._last_mouse == (0, 0):
                cw = max(1, self.canvas.winfo_width())
                ch = max(1, self.canvas.winfo_height())
                self._last_mouse = (cw // 2, ch // 2)
            self._update_turret()
        else:
            # unbind and remove turret
            self.canvas.unbind("<Motion>")
            self._destroy_turret_items()

    def _pv_draw_rounded_bubble(self, bx1, by1, bx2, by2, radius, tail_tip, fill, state="hidden"):
        # Jednolite rysowanie poligonem, żeby uniknąć „szwów” i kresek
        items = []
        r = max(2, int(radius))
        r = min(r, abs(bx2 - bx1)//2, abs(by2 - by1)//2)

        # funkcja do próbkowania łuku
        def arc(cx, cy, rad, a0_deg, a1_deg, steps=8):
            pts = []
            a0 = math.radians(a0_deg)
            a1 = math.radians(a1_deg)
            da = (a1 - a0) / max(1, steps)
            for i in range(steps + 1):
                a = a0 + i * da
                pts.append((cx + rad*math.cos(a), cy + rad*math.sin(a)))
            return pts

        # cztery narożniki (kolejno zgodnie z ruchem wskazówek)
        pts = []
        pts += arc(bx2 - r, by1 + r, r, 270, 360, steps=10)   # top-right
        pts += [(bx2, by1 + r), (bx2, by2 - r)]               # prawa prosta
        pts += arc(bx2 - r, by2 - r, r, 0, 90, steps=10)      # bottom-right

        # ogon (trójkąt)
        base1 = (bx2 - r*0.8, by2 - r*0.4)
        base2 = (bx2 - r*0.2, by2 + r*0.2)
        pts += [base1, (tail_tip[0], tail_tip[1]), base2]

        pts += [(bx1 + r, by2), (bx1 + r, by2)]
        pts += arc(bx1 + r, by2 - r, r, 90, 180, steps=10)    # bottom-left
        pts += [(bx1, by2 - r), (bx1, by1 + r)]               # lewa prosta
        pts += arc(bx1 + r, by1 + r, r, 180, 270, steps=10)   # top-left

        flat = []
        for x, y in pts:
            flat.extend((x, y))

        poly = self.canvas.create_polygon(
            *flat, fill=fill, outline="", width=0, state=state, smooth=True
        )

        items.append(poly)
        return items

    def _pv_set_items_state(self, items, state):
        for it in items or []:
            try:
                self.canvas.itemconfig(it, state=state)
            except Exception:
                pass

    def _pv_set_items_fill(self, items, fill):
        for it in items or []:
            try:
                self.canvas.itemconfig(it, fill=fill, outline="")
            except Exception:
                pass

    def _pv_raise(self, items):
        for it in items or []:
            try:
                self.canvas.tag_raise(it)
            except Exception:
                pass

    def _create_turret_items(self):
        # create if not present
        if self._turret["base"] is not None:
            return
        r = self._turret["radius"]
        px, py = self._get_turret_pivot()

        # base (circle)
        base = self.canvas.create_oval(px - r, py - r, px + r, py + r, width=2)

        # pedestal (subtle, turret-ish)
        ped_w = int(r * 1.4)
        pedestal = self.canvas.create_rectangle(
            px - ped_w, py + r + 2, px + ped_w, py + r + 10, width=0, fill=""
        )

        # barrel (line)
        barrel_len = int(r * 1.6)
        barrel = self.canvas.create_line(
            px, py, px + barrel_len, py,
            width=4, capstyle=tk.ROUND, fill="#ff2b2b"
        )

        # rounded bubble items (hidden initially)
        bw, bh = 172, 34
        bx1 = max(6, px - bw - 14)
        by1 = max(6, py - r - 14 - bh)
        bx2 = bx1 + bw
        by2 = by1 + bh
        tail_tip = (px - r - 2, py - r - 2)
        col = self._theme_colors()
        bubble_items = self._pv_draw_rounded_bubble(
            bx1, by1, bx2, by2, 10, tail_tip, col.get("bubble_fill", "#f5f5f5"), state="hidden"
        )

        bubble_text = self.canvas.create_text((bx1 + bx2)//2, (by1 + by2)//2,
                                      text="Are you still there?",
                                      font=("Segoe UI", 11, "bold"),
                                      fill="#00FFFF",
                                      state="hidden")

        self._turret["base"] = base
        self._turret["barrel"] = barrel
        self._turret["pedestal"] = pedestal
        self._turret["bubble_items"] = bubble_items
        self._turret["bubble_text"] = bubble_text
        self._turret["bubble_rect"] = None # not using rect
        self._turret["tail"] = None # not using default tail

        # keep turret above image
        self.canvas.tag_raise(pedestal)
        self.canvas.tag_raise(base)
        self.canvas.tag_raise(barrel)
        self._pv_raise(bubble_items)
        self.canvas.tag_raise(bubble_text)

        self._apply_turret_theme()

    def _destroy_turret_items(self):
        for key in ("base", "barrel", "bubble_rect", "bubble_text", "tail", "pedestal"):
            if self._turret.get(key) is not None:
                try:
                    self.canvas.delete(self._turret[key])
                except:
                    pass
                self._turret[key] = None

        for it in self._turret.get("bubble_items", []):
            try: self.canvas.delete(it)
            except Exception: pass
        self._turret["bubble_items"] = []

    def _get_turret_pivot(self):
        self.canvas.update_idletasks()
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        margin = self._turret["margin"]
        r = self._turret["radius"]
        return (cw - margin - r, ch - margin - r)

    def _position_turret(self):
        if not self.turret_mode or self._turret["base"] is None:
            return
        r = self._turret["radius"]
        px, py = self._get_turret_pivot()

        # move base
        self.canvas.coords(self._turret["base"], px - r, py - r, px + r, py + r)

        # pedestal
        ped_w = int(r * 1.4)
        if self._turret.get("pedestal"):
            self.canvas.coords(self._turret["pedestal"], px - ped_w, py + r + 2, px + ped_w, py + r + 10)

        # barrel handled in update

        # position bubble roughly above-left
        bw, bh = 172, 34
        bx1 = max(6, px - bw - 14)
        by1 = max(6, py - r - 14 - bh)
        bx2 = bx1 + bw
        by2 = by1 + bh

        # rebuild rounded bubble at new position
        try:
            # delete previous rounded bubble items
            if self._turret.get("bubble_items"):
                for it in self._turret["bubble_items"]:
                    try:
                        self.canvas.delete(it)
                    except Exception:
                        pass
                self._turret["bubble_items"] = []

            tail_tip = (px - r - 2, py - r - 2)
            col = self._theme_colors()
            self._turret["bubble_items"] = self._pv_draw_rounded_bubble(
                bx1, by1, bx2, by2, 10, tail_tip, col.get("bubble_fill", "#f5f5f5"), state="hidden"
            )

            # center text
            if self._turret.get("bubble_text"):
                self.canvas.coords(self._turret["bubble_text"], (bx1 + bx2)//2, (by1 + by2)//2)

            # z-order
            if self._turret.get("pedestal"):
                self.canvas.tag_raise(self._turret["pedestal"])
            if self._turret.get("base"):
                self.canvas.tag_raise(self._turret["base"])
            if self._turret.get("barrel"):
                self.canvas.tag_raise(self._turret["barrel"])
            self._pv_raise(self._turret["bubble_items"])
            if self._turret.get("bubble_text"):
                self.canvas.tag_raise(self._turret["bubble_text"])

        except Exception:
            pass

        self._update_turret()

    def _on_mouse_move(self, event):
        self._last_mouse = (event.x, event.y)
        self._update_turret()

    def _theme_colors(self):
        if self.theme == "light":
            return dict(base_fill="#e6e6e6", base_outline="#888",
                        barrel="#444",
                        bubble_fill="#f5f5f5", bubble_outline="#999", bubble_text="#000")
        else:
            return dict(base_fill="#3a3a3a", base_outline="#777",
                        barrel="#eaeaea",
                        bubble_fill="#222", bubble_outline="#666", bubble_text="#fff")

    def _apply_turret_theme(self):
        if not self.turret_mode or self._turret["base"] is None:
            return
        col = self._theme_colors()
        try:
            self.canvas.itemconfig(self._turret["base"], fill=col["base_fill"], outline=col["base_outline"])
            self.canvas.itemconfig(self._turret["barrel"], fill="#ff2b2b", width=4)

            self._pv_set_items_fill(self._turret.get("bubble_items", []), col.get("bubble_fill", "#f5f5f5"))
            self.canvas.itemconfig(self._turret["bubble_text"], fill=col["bubble_text"])

            ped_fill = "#2f2f2f" if getattr(self, "theme", "dark") == "dark" else "#e0e0e0"
            if self._turret.get("pedestal"):
                self.canvas.itemconfig(self._turret["pedestal"], fill=ped_fill, outline="")

        except:
            pass

    def _update_turret(self):
        if not self.turret_mode or self._turret["base"] is None:
            return
        px, py = self._get_turret_pivot()
        mx, my = self._last_mouse

        # aim barrel to cursor
        dx = mx - px
        dy = my - py
        angle = math.atan2(dy, dx)
        r = self._turret["radius"]
        barrel_len = int(r * 1.8)
        ex = px + int(barrel_len * math.cos(angle))
        ey = py + int(barrel_len * math.sin(angle))
        self.canvas.coords(self._turret["barrel"], px, py, ex, ey)

        # show/hide bubble if cursor within 100 px
        dist = math.hypot(dx, dy)
        state = "normal" if dist <= 100 else "hidden"
        try:
            self._pv_set_items_state(self._turret.get("bubble_items", []), state)
            self.canvas.itemconfig(self._turret["bubble_text"], state=state)
        except:
            pass

        # ensure turret remains on top of image
        if self._turret.get("pedestal"):
            self.canvas.tag_raise(self._turret["pedestal"])
        for key in ("base", "barrel"):
            try:
                self.canvas.tag_raise(self._turret[key])
            except:
                pass
        self._pv_raise(self._turret.get("bubble_items", []))
        if self._turret.get("bubble_text"):
            self.canvas.tag_raise(self._turret["bubble_text"])

    # ================= Dominant Colors Palette (Ctrl+B) =================
    
    def _dc_rgb_to_hex(self, rgb):
        return "#{:02X}{:02X}{:02X}".format(*rgb)

    def _dc_extract_palette(self, n=5):
        # Use currently displayed image if available
        im = getattr(self, "displayed_image", None) or getattr(self, "image", None)
        if im is None:
            return []

        # Composite on app background to avoid counting transparency as black
        img = im.convert("RGBA")
        try:
            bg_hex = getattr(self, "bg", "#1c1c1c")
        except Exception:
            bg_hex = "#1c1c1c"
        bg = Image.new("RGBA", img.size, bg_hex)
        img = Image.alpha_composite(bg, img)

        # Downscale for speed
        max_side = 480
        w, h = img.size
        scale = min(max_side / w, max_side / h, 1.0)
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        # Median-cut quantization to N colors
        q = img.convert("RGB").quantize(colors=n, method=Image.MEDIANCUT)
        counts = q.getcolors(maxcolors=img.size[0] * img.size[1])
        if not counts:
            return []

        # Map palette indexes back to RGB when needed
        palette_raw = q.getpalette()[:256 * 3] if q.mode == "P" else None
        total = sum(c for c, _ in counts)
        counts.sort(reverse=True)  # most frequent first
        top = []
        for cnt, val in counts[:n]:
            if isinstance(val, int) and palette_raw is not None:
                r = palette_raw[val * 3]
                g = palette_raw[val * 3 + 1]
                b = palette_raw[val * 3 + 2]
                rgb = (r, g, b)
            else:
                rgb = val if isinstance(val, tuple) else (0, 0, 0)
            top.append((self._dc_rgb_to_hex(rgb), rgb, round(cnt / total * 100.0, 1)))
        return top

    def _dc_palette_apply_theme(self):
        win = getattr(self, "_palette_win", None)
        if not win or not win.winfo_exists():
            return
        try:
            bg = getattr(self, "bg", "#1c1c1c")
            fg = getattr(self, "fg", "#ffffff")
            card_bg = getattr(self, "card_bg", bg)
        except Exception:
            bg, fg, card_bg = "#1c1c1c", "#ffffff", "#1f1f1f"

        win.configure(fg_color=bg)
        for child in win.winfo_children():
            try:
                # Header or any labels
                if child.__class__.__name__ == "CTkLabel":
                    child.configure(text_color=fg)
                # Content frames
                if child is getattr(win, "_list_frame", None):
                    child.configure(fg_color=card_bg)
                    for row in child.winfo_children():
                        for wdg in row.winfo_children():
                            if wdg.__class__.__name__ == "CTkLabel":
                                wdg.configure(text_color=fg)
            except Exception:
                pass

    def _dc_open_palette_window(self, event=None):
        # Compute palette first, so we can show an up-to-date preview
        palette = self._dc_extract_palette(5)
        if not palette:
            try:
                messagebox.showinfo("TurretEye", "Najpierw otwórz obraz, aby wykryć kolory.")
            except Exception:
                pass
            return
        self._palette_colors = palette

        # Create window if needed
        if not getattr(self, "_palette_win", None) or not self._palette_win.winfo_exists():
            win = ctk.CTkToplevel(self.root)
            self._palette_win = win
            win.title("Paleta kolorów — TurretEye")
            win.geometry("460x360")
            win.resizable(False, False)
            try:
                win.attributes("-topmost", True)
            except Exception:
                pass

            # Header
            header = ctk.CTkLabel(win, text="Paleta kolorów", font=("Segoe UI", 14, "bold"))
            header.pack(padx=12, pady=(12, 8))

            # List container
            list_frame = ctk.CTkFrame(win)
            list_frame.pack(fill="both", expand=True, padx=12, pady=8)
            win._list_frame = list_frame

            # Buttons
            btns = ctk.CTkFrame(win, fg_color="transparent")
            btns.pack(fill="x", padx=12, pady=(4, 12))
            save_btn = ctk.CTkButton(btns, text="Zapisz paletę jako PNG", command=self._dc_save_palette_png)
            save_btn.pack(side="right")
            win.bind("<Escape>", lambda e: win.destroy())

        # (Re)build rows
        lf = self._palette_win._list_frame
        for ch in lf.winfo_children():
            ch.destroy()

        border = getattr(self, "border", "#2b2b2b")
        for idx, (hexv, rgb, pct) in enumerate(palette, start=1):
            row = ctk.CTkFrame(lf, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=6)

            sw = tk.Canvas(row, width=38, height=38, highlightthickness=1)
            try:
                sw.configure(background=hexv, highlightbackground=border)
            except Exception:
                sw.configure(bg=hexv, highlightbackground=border)
            sw.pack(side="left")

            lbl = ctk.CTkLabel(row, text=f"{idx}. {hexv} — {pct}%", font=("Segoe UI", 12))
            lbl.pack(side="left", padx=12)

        self._dc_palette_apply_theme()

    def _dc_save_palette_png(self):
        palette = getattr(self, "_palette_colors", None) or self._dc_extract_palette(5)
        if not palette:
            return

        n = len(palette)
        cell_w, cell_h = 220, 220
        margin, gap = 24, 12
        width = margin * 2 + n * cell_w + (n - 1) * gap
        height = margin * 2 + cell_h

        bg = getattr(self, "bg", "#1c1c1c")
        fg = getattr(self, "fg", "#ffffff")

        out = Image.new("RGB", (width, height), bg)
        draw = ImageDraw.Draw(out)
        try:
            font = ImageFont.truetype("arial.ttf", 18)
        except Exception:
            try:
                font = ImageFont.truetype("DejaVuSans.ttf", 18)
            except Exception:
                font = ImageFont.load_default()

        for i, (hexv, rgb, pct) in enumerate(palette):
            x = margin + i * (cell_w + gap)
            y = margin
            swatch_h = int(cell_h * 0.72)
            draw.rectangle([x, y, x + cell_w, y + swatch_h], fill=hexv, outline="#000000")
            label = f"{hexv}  {pct}%"
            try:
                # Pillow <10
                tw, th = draw.textsize(label, font=font)
            except AttributeError:
                # Pillow ≥10
                bbox = draw.textbbox((0, 0), label, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx = x + (cell_w - tw) / 2
            ty = y + swatch_h + (cell_h - swatch_h - th) / 2
            draw.text((tx, ty), label, font=font, fill=fg)

        initial_dir = getattr(self, "last_dir", "") or ""
        default_name = "palette.png"
        path = filedialog.asksaveasfilename(
            parent=self.root,
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
            initialfile=default_name,
            initialdir=initial_dir,
            title="Zapisz paletę jako PNG",
        )
        if path:
            out.save(path)
            try:
                self.status.set(f"Zapisano paletę: {path}")
            except Exception:
                pass

    # ===================== Navigation Window (Okno Nawigacji) =====================

    def _nav_init_fields(self):
        self._nav_win = None
        self._nav_panel = None
        self._nav_btns = []
        self._nav_photo_refs = {}
        self._nav_on_top = False

    def _nav_accent(self):
        try:
            dark = self.theme == "dark"
        except Exception:
            dark = True
        return "#3a82f7" if dark else "#1e5fbf"

    def _nav_open_window(self, event=None):
        try:
            if self._nav_win is not None and self._nav_win.winfo_exists():
                self._nav_win.deiconify()
                self._nav_win.focus_force()
                self._nav_update_highlight()
                return

            top = ctk.CTkToplevel(self.root)
            top.title("Okno nawigacji — miniatury (Ctrl+T)")
            top.geometry("1200x300+80+80")
            top.configure(fg_color=self.bg)
            top.attributes("-topmost", self._nav_on_top)
            self._nav_win = top

            def _on_close():
                try:
                    if self._nav_win is not None and self._nav_win.winfo_exists():
                        self._nav_win.destroy()
                finally:
                    self._nav_win = None
                    self._nav_panel = None
                    self._nav_btns = []
                    self._nav_photo_refs = {}

            top.protocol("WM_DELETE_WINDOW", _on_close)

            ctrl = ctk.CTkFrame(top, fg_color=self.bg)
            ctrl.pack(fill="x", padx=14, pady=(14, 8))
            self._nav_on_top_var = ctk.BooleanVar(value=self._nav_on_top)
            def _toggle_top():
                self._nav_on_top = bool(self._nav_on_top_var.get())
                self._nav_win.attributes("-topmost", self._nav_on_top)
            ctk.CTkCheckBox(ctrl, text="Zawsze na wierzchu", variable=self._nav_on_top_var,
                            text_color=self.fg, fg_color=self.btn_bg, hover_color=self.hover_bg,
                            command=_toggle_top).pack(side="left", padx=(0,8))
            ctk.CTkButton(ctrl, text="Odśwież", fg_color=self.btn_bg, hover_color=self.hover_bg,
                          text_color=self.fg, command=self._nav_refresh).pack(side="left", padx=(0,8))
            ctk.CTkButton(ctrl, text="Zamknij", fg_color=self.btn_bg, hover_color=self.hover_bg,
                          text_color=self.fg, command=_on_close).pack(side="left")

            self._nav_panel = ctk.CTkScrollableFrame(top, fg_color=self.bg, orientation="horizontal")
            self._nav_panel.pack(fill="both", expand=True, padx=14, pady=(6, 14))

            self._nav_win.bind("<Left>", lambda e: self._nav_arrow_prev())
            self._nav_win.bind("<Right>", lambda e: self._nav_arrow_next())

            self._nav_refresh()
            self._nav_apply_theme()

        except Exception as e:
            print("Navigation window error:", e)

    def _nav_build_padded(self, pil_img):
        canvas = Image.new("RGBA", self._THUMB_SIZE, (0,0,0,0))
        img = pil_img.copy()
        img.thumbnail(self._THUMB_INNER, Image.LANCZOS)
        x = (canvas.width - img.width)//2
        y = (canvas.height - img.height)//2
        canvas.paste(img, (x, y), img if img.mode in ("RGBA", "LA") else None)
        return canvas

    def _nav_get_thumb(self, path):
        try:
            img_th = self.thumb_cache.get(path)
            if img_th is None:
                ext = os.path.splitext(path)[1].lower()
                if ext in self._RAW_EXT:
                    with rawpy.imread(path) as raw:
                        rgb = raw.postprocess(use_auto_wb=True, no_auto_bright=True, output_bps=8)
                        base = Image.fromarray(rgb).convert("RGBA")
                else:
                    base = self._open_image_with_ico_support(path)
                img_th = base.copy()
                img_th.thumbnail(self._THUMB_INNER, Image.LANCZOS)
                self.thumb_cache[path] = img_th

            padded = self._nav_build_padded(img_th)
            ph = ctk.CTkImage(light_image=padded, dark_image=padded, size=self._THUMB_SIZE)
            self._nav_photo_refs[path] = ph
            return padded, ph
        except Exception as e:
            print("Thumb error:", e, "for", path)
            return None, None

    def _nav_refresh(self):
        if self._nav_panel is None or not self._nav_panel.winfo_exists():
            return
        for w in self._nav_panel.winfo_children():
            try: w.destroy()
            except Exception: pass
        self._nav_btns.clear()
        files = list(self.image_list)
        if not files:
            ctk.CTkLabel(self._nav_panel, text="Brak obrazów",
                         text_color=self.fg, font=("Segoe UI", 14, "italic")).pack(pady=18)
            return

        col = 0
        for idx, path in enumerate(files):
            _, ph = self._nav_get_thumb(path)
            base = os.path.basename(path)
            # nazwa + rozdzielczość
            try:
                if path in self._img_size_cache:
                    w, h = self._img_size_cache[path]
                else:
                    with Image.open(path) as _im:
                        w, h = _im.size
                    self._img_size_cache[path] = (w, h)
                text = (base if len(base) <= 22 else base[:19] + "...") + f" ({w}x{h})"
            except Exception:
                text = base if len(base) <= 26 else base[:23] + "..."
            btn = ctk.CTkButton(self._nav_panel, image=ph, text=text, compound="top",
                                width=self._THUMB_SIZE[0]+16, height=self._THUMB_SIZE[1]+40,
                                fg_color=self.btn_bg, hover_color=self.hover_bg,
                                text_color=self.fg, corner_radius=14,
                                command=lambda i=idx: self._nav_on_click(i))
            btn.grid(row=0, column=col, padx=8, pady=8, sticky="n")
            self._nav_btns.append(btn)
            col += 1
        self._nav_update_highlight()
        try: self._nav_scroll_to_index(self.current_image_index)
        except Exception: pass

    
    def _nav_update_highlight(self):
            """
            Visually mark the active thumbnail. Uses an accent background color for the
            active thumbnail button (more visible and more reliable than border-only).
            This will be called after image changes to keep the navigation view in sync.
            """
            try:
                if not getattr(self, "_nav_btns", None):
                    return
                # get accent color (fall back to a sensible blue)
                try:
                    accent = self._nav_accent()
                except Exception:
                    accent = "#3a82f7"
                # ensure index is valid
                try:
                    act = int(self.current_image_index)
                except Exception:
                    act = 0
                for i, btn in enumerate(self._nav_btns):
                    try:
                        if not btn.winfo_exists():
                            continue
                    except Exception:
                        continue
                    if i == act:
                        # Active: set a visible accent background and readable text color.
                        # Most reliable to set fg_color; fall back to border if unavailable.
                        try:
                            btn.configure(fg_color=accent, hover_color=self.hover_bg, text_color=self.fg)
                            # If the button supports changing corner radius it will keep it.
                            try:
                                btn.configure(corner_radius=14)
                            except Exception:
                                pass
                        except Exception:
                            try:
                                btn.configure(border_width=3, border_color=accent)
                            except Exception:
                                pass
                    else:
                        # Reset to default theme look
                        try:
                            btn.configure(fg_color=self.btn_bg, hover_color=self.hover_bg, text_color=self.fg)
                            try:
                                btn.configure(border_width=0)
                            except Exception:
                                pass
                        except Exception:
                            pass
            except Exception as e:
                print("Nav highlight error:", e)

    def _nav_scroll_to_index(self, index):
        """
        Ensure the thumbnail at `index` is fully visible in the horizontal scroll area.
        This implementation is optimized for speed (minimal geometry queries) and uses
        after_idle to allow geometry to settle without blocking. It centers the thumbnail
        where possible but always ensures the thumbnail is entirely within the viewport.
        """
        try:
            nav_panel = getattr(self, "_nav_panel", None)
            if nav_panel is None or not getattr(nav_panel, "winfo_exists", lambda: False)():
                return

            nav_btns = getattr(self, "_nav_btns", None) or []
            if not nav_btns:
                return
            if index < 0 or index >= len(nav_btns):
                return

            # Use a short, non-blocking callback so layout can settle first
            def _do_scroll():
                try:
                    btn = nav_btns[index]

                    # Try to get internal canvas quickly; avoid heavy searches repeatedly
                    canvas = getattr(nav_panel, "_canvas", None)
                    if canvas is None:
                        for attr in ("_parent_canvas", "canvas", "_viewport", "_ctk_canvas"):
                            canvas = getattr(nav_panel, attr, None)
                            if canvas is not None:
                                break

                    if canvas is None:
                        try:
                            for child in nav_panel.winfo_children():
                                try:
                                    if child.winfo_class().lower() == "canvas":
                                        canvas = child
                                        break
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    if canvas is None:
                        return

                    try:
                        cw = canvas.winfo_width()
                    except Exception:
                        cw = 0

                    inner = getattr(nav_panel, "_scrollable_frame", None)
                    if inner is not None:
                        total_w = inner.winfo_width()
                    else:
                        try:
                            bbox = canvas.bbox("all")
                            total_w = bbox[2] if bbox and len(bbox) >= 3 else canvas.winfo_width()
                        except Exception:
                            total_w = canvas.winfo_width()

                    if cw <= 0 or total_w <= cw:
                        return

                    bx = btn.winfo_x()
                    bw = btn.winfo_width()

                    try:
                        x0 = canvas.canvasx(0)
                        x1 = x0 + cw
                    except Exception:
                        x0 = 0
                        x1 = cw

                    margin = 12

                    if bx >= x0 + margin and (bx + bw) <= x1 - margin:
                        return

                    if bw >= cw:
                        target_left = bx
                    else:
                        if bx < x0 + margin:
                            target_left = max(0, bx - margin)
                        else:
                            target_left = min(max(0, total_w - cw), bx + bw + margin - cw)

                    frac = target_left / max(1, (total_w - cw))
                    try:
                        canvas.xview_moveto(frac)
                    except Exception:
                        try:
                            canvas.xview('moveto', frac)
                        except Exception:
                            pass

                except Exception as e:
                    print("Nav scroll error (do_scroll):", e)

            try:
                nav_panel.after_idle(_do_scroll)
            except Exception:
                _do_scroll()

        except Exception as e:
            print("Nav scroll error:", e)


    def _nav_on_click(self, index):
        try:
            if not self.image_list:
                return
            index = max(0, min(index, len(self.image_list)-1))
            self.current_image_index = index
            self._update_counter_overlay()
            self.display_image()
            self.save_last_session()
            self._nav_update_highlight()
            self._nav_scroll_to_index(index)
        except Exception as e:
            print("Nav click err:", e)

    def _nav_apply_theme(self):
        try:
            if self._nav_win is None or not self._nav_win.winfo_exists():
                return
            self._nav_win.configure(fg_color=self.bg)
            if self._nav_panel and self._nav_panel.winfo_exists():
                self._nav_panel.configure(fg_color=self.bg)
            for btn in self._nav_btns:
                btn.configure(fg_color=self.btn_bg, hover_color=self.hover_bg, text_color=self.fg)
            self._nav_update_highlight()
        except Exception:
            pass

    def _nav_arrow_prev(self):
        try:
            if self.image_list and self.current_image_index > 0:
                self.current_image_index -= 1
                self._update_counter_overlay()
                self.display_image()
                self.save_last_session()
                self._nav_update_highlight()
                self._nav_scroll_to_index(self.current_image_index)
        except Exception:
            pass

    def _nav_arrow_next(self):
        try:
            if self.image_list and self.current_image_index < len(self.image_list) - 1:
                self.current_image_index += 1
                self._update_counter_overlay()
                self.display_image()
                self.save_last_session()
                self._nav_update_highlight()
                self._nav_scroll_to_index(self.current_image_index)
        except Exception:
            pass


active_menu = None

# ---------- CustomContextMenu (beznadzorowy, estetyczny) ----------
class CustomContextMenu(ctk.CTkToplevel):
    def __init__(self, master, commands: dict, theme: str, x: int, y: int, parent=None):
        super().__init__(master)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.theme = theme
        self.commands = commands
        self.submenu = None
        self.parent = parent

        self.bg = "#2b2b2b" if self.theme == "dark" else "#f5f5f5"
        self.fg = "#ffffff" if self.theme == "dark" else "#000000"
        self.hover = "#3d3d3d" if self.theme == "dark" else "#dddddd"

        self.frame = tk.Frame(self, bg=self.bg, bd=0, highlightthickness=0)
        self.frame.pack()

        self.font = tkFont.Font(family="Segoe UI", size=11)
        self.max_text_width = self.calculate_max_text_width()
        self.build_menu()

        self.configure(bg=self.bg)
        try:
            self.wm_attributes("-alpha", 0.96)
        except:
            pass

        self.update_idletasks()
        width = self.max_text_width
        height = self.frame.winfo_height()
        # safety: minimal width
        if width < 120:
            width = 120
        if height < 30:
            height = 30
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()

        global active_menu
        if self.parent is None:
            if active_menu:
                try:
                    active_menu.destroy()
                except:
                    pass
            active_menu = self

        self.bind_click_outside()

    def bind_click_outside(self):
        self.master.bind("<Button-1>", self.on_click_outside)

    def on_click_outside(self, event):
        if not self._is_inside(self, event.x_root, event.y_root):
            self.close_all_menus()

    def calculate_max_text_width(self):
        max_width = 0
        for text, command in self.commands.items():
            if text == "---":
                continue
            display_text = text + " ▶" if isinstance(command, dict) else text
            text_width = self.font.measure(display_text)
            max_width = max(max_width, text_width)
        return max_width + 40

    def build_menu(self):
        for text, command in self.commands.items():
            if text == "---":
                sep = tk.Frame(self.frame, height=1, bg="#666" if self.theme == "dark" else "#bbb")
                sep.pack(fill="x", padx=14, pady=6)
                continue
            display_text = text + " ▶" if isinstance(command, dict) else text
            btn = tk.Label(self.frame, text=display_text, bg=self.bg, fg=self.fg,
                           anchor="w", padx=20, pady=8, font=self.font)
            btn.pack(fill="x")
            if isinstance(command, dict):
                btn.bind("<Enter>", lambda e, b=btn, c=command: [b.configure(bg=self.hover), self.open_submenu(b, c)])
                btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=self.bg))
            else:
                btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=self.hover))
                btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=self.bg))
                btn.bind("<Button-1>", lambda e, cmd=command: [cmd(), self.close_all_menus()])

    def open_submenu(self, widget, submenu_dict):
        if self.submenu:
            try:
                self.submenu.destroy()
            except:
                pass
        x = widget.winfo_rootx() + widget.winfo_width() - 1
        y = widget.winfo_rooty()
        self.submenu = CustomContextMenu(self, submenu_dict, self.theme, x, y, parent=self)

    def _is_inside(self, win, x, y):
        if not win:
            return False
        try:
            return (win.winfo_rootx() <= x <= win.winfo_rootx() + win.winfo_width() and
                    win.winfo_rooty() <= y <= win.winfo_rooty() + win.winfo_height())
        except:
            return False

    def close_all_menus(self):
        if self.submenu:
            try:
                self.submenu.destroy()
            except:
                pass
        if self.parent is None:
            global active_menu
            if active_menu:
                try:
                    active_menu.destroy()
                except:
                    pass
                active_menu = None


if __name__ == "__main__":
    try:
        root = TkinterDnD.Tk()

        try:
            if hasattr(sys, "_MEIPASS"):
                icon_path = os.path.join(sys._MEIPASS, "TurretEye.ico")
            else:
                icon_path = os.path.join(os.path.dirname(__file__), "TurretEye.ico")

            # ustawienie ikony okna
            root.iconbitmap(icon_path)
            root.tk.call('wm', 'iconbitmap', root._w, icon_path)

            # ustawienie ikony procesu (taskbar) przez WinAPI
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TurretEye")
        except Exception as e:
            print("Nie udało się ustawić ikony:", e)

        app = TurretEyeApp(root)
        root.mainloop()
    except Exception:
        error_msg = traceback.format_exc()
        print(error_msg)
        tk.messagebox.showerror("Błąd krytyczny", error_msg)
