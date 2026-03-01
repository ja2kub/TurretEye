# -*- coding: utf-8 -*-

# --- Constants & Config ---
SESSION_FILE = "last_session.pkl"
RAW_EXT = (".cr2", ".nef", ".arw", ".dng")
THUMB_WIDTH = 120
THUMB_HEIGHT = 100

# Translations
TRANS = {
    "pl": {
        "btn_file": "Plik", "btn_folder": "Folder", "btn_save": "Zapisz", "btn_edit": "Edycja", "btn_theme": "Motyw",
        "btn_prev": "Poprzedni", "btn_next": "Następny", "btn_zoom_in": "Powiększ", "btn_zoom_out": "Pomniejsz",
        "btn_rot_l": "Obróć w lewo", "btn_rot_r": "Obróć w prawo", "btn_full": "Pełny ekran",
        "btn_nav": "Nawigacja", "btn_help": "Pomoc",
        "ctx_rot_l": "Obróć w lewo", "ctx_rot_r": "Obróć w prawo", "ctx_full": "Pełny ekran", "ctx_undo": "Cofnij",
        "ctx_style": "Stylizacja AI", "style_sketch": "Szkic", "style_oil": "Obraz olejny", "style_sepia": "Sepia", "style_contrast": "Kontrast", "style_bw": "Czarno-biały",
        "url_title": "Wklej URL obrazu", "url_lbl": "URL:", "url_load": "Załaduj", "url_cancel": "Anuluj", "url_downloading": "Pobieranie...", "url_err_title": "Błąd", "url_err_msg": "Nie udało się pobrać obrazu:\n{}",
        "save_title": "Zapisz jako", "save_msg": "Zapisano do:\n{}", "save_info": "Zapisano",
        "pdf_title": "Eksport PDF", "pdf_success": "PDF zapisany.", "pdf_err_title": "Błąd",
        "pdf_folder_title": "Folder do PDF", "pdf_bg_info": "Eksport rozpoczęty w tle...", "pdf_bg_title": "Info",
        "pdf_worker_success": "Eksport PDF zakończony sukcesem!", "pdf_worker_err": "Błąd eksportu: {}", "pdf_box_title": "PDF Eksport",
        "nav_title": "Nawigacja",
        "help_title": "Skróty klawiszowe",
        "pal_title": "Paleta kolorów", "pal_save": "Zapisz jako PNG", "pal_dlg_save": "Zapisz",
        "edit_title": "Edycja", "edit_bright": "Jasność", "edit_sat": "Nasycenie", "edit_sharp": "Ostrość",
        "edit_hover_border": "Kolor obramowania najechania",
        "edit_hover_border_placeholder": "np. #C6E6F8 / #80C6E6F8 / transparent",
        "edit_pick_color": "Wybierz kolor",
        "edit_apply_color": "Zastosuj",
        "edit_hover_border_invalid_title": "Nieprawidłowy kolor",
        "edit_hover_border_invalid_msg": "Podaj poprawny kolor, np. #C6E6F8, #80C6E6F8 albo transparent.",
        "turret_msg": "Are you still there?",
        "file_dialog_img": "Wybierz obraz", "file_dialog_folder": "Wybierz folder",
        "status_url": "URL: {}",
        "h_prev": "Poprzedni / następny", "h_zoom": "Zoom", "h_full": "Pełny ekran", "h_rot": "Obrót", "h_url": "URL", "h_pal": "Paleta", "h_mir": "Lustro", "h_pdf": "PDF", "h_slide": "Pokaz slajdów", "h_undo": "Cofnij/Ponów", "h_turret": "Turret Mode", "h_scroll": "Kółko", "h_pan": "LPM+Drag", "h_lang": "Zmiana języka",
        "open_with_url": "Otwórz z URL", "enter_link": "Podaj bezpośredni link do obrazu:"
    },
    "en": {
        "btn_file": "File", "btn_folder": "Folder", "btn_save": "Save", "btn_edit": "Edit", "btn_theme": "Theme",
        "btn_prev": "Previous", "btn_next": "Next", "btn_zoom_in": "Zoom in", "btn_zoom_out": "Zoom out",
        "btn_rot_l": "Rotate left", "btn_rot_r": "Rotate right", "btn_full": "Fullscreen",
        "btn_nav": "Navigation", "btn_help": "Help",
        "ctx_rot_l": "Rotate Left", "ctx_rot_r": "Rotate Right", "ctx_full": "Fullscreen", "ctx_undo": "Undo",
        "ctx_style": "AI Styling", "style_sketch": "Sketch", "style_oil": "Oil Paint", "style_sepia": "Sepia", "style_contrast": "Contrast", "style_bw": "Black & White",
        "url_title": "Paste Image URL", "url_lbl": "URL:", "url_load": "Load", "url_cancel": "Cancel", "url_downloading": "Downloading...", "url_err_title": "Error", "url_err_msg": "Failed to download image:\n{}",
        "save_title": "Save As", "save_msg": "Saved to:\n{}", "save_info": "Saved",
        "pdf_title": "Export PDF", "pdf_success": "PDF saved.", "pdf_err_title": "Error",
        "pdf_folder_title": "Folder to PDF", "pdf_bg_info": "Export started in background...", "pdf_bg_title": "Info",
        "pdf_worker_success": "PDF export finished successfully!", "pdf_worker_err": "Export error: {}", "pdf_box_title": "PDF Export",
        "nav_title": "Navigation",
        "help_title": "Keyboard Shortcuts",
        "pal_title": "Color Palette", "pal_save": "Save as PNG", "pal_dlg_save": "Save",
        "edit_title": "Edit", "edit_bright": "Brightness", "edit_sat": "Saturation", "edit_sharp": "Sharpness",
        "edit_hover_border": "Hover outline color",
        "edit_hover_border_placeholder": "e.g. #C6E6F8 / #80C6E6F8 / transparent",
        "edit_pick_color": "Pick color",
        "edit_apply_color": "Apply",
        "edit_hover_border_invalid_title": "Invalid color",
        "edit_hover_border_invalid_msg": "Enter a valid color, e.g. #C6E6F8, #80C6E6F8 or transparent.",
        "turret_msg": "Are you still there?",
        "file_dialog_img": "Select Image", "file_dialog_folder": "Select Folder",
        "status_url": "URL: {}",
        "h_prev": "Prev / Next", "h_zoom": "Zoom", "h_full": "Fullscreen", "h_rot": "Rotation", "h_url": "URL", "h_pal": "Palette", "h_mir": "Mirror", "h_pdf": "PDF", "h_slide": "Slideshow", "h_undo": "Undo/Redo", "h_turret": "Turret Mode", "h_scroll": "Wheel", "h_pan": "LMB+Drag", "h_lang": "Change Language",
        "open_with_url": "Open from URL", "enter_link": "Enter direct image link:"
    }
}

# Colors extracted from original
THEME_DARK = {
    "bg": "#0f1012", "bg_alt": "#17191d",
    "fg": "#f2f2f3", "muted_fg": "#a3a7ae",
    "btn_bg": "rgba(34, 36, 41, 0.92)", "hover_bg": "rgba(51, 54, 61, 0.95)",
    "card_bg": "rgba(25, 27, 31, 0.92)", "card_bg_2": "rgba(19, 21, 25, 0.96)",
    "border": "rgba(255, 255, 255, 0.10)", "accent": "#ff5e64",
    "turret_base_fill": "#3a3a3a", "turret_base_outline": "#777",
    "turret_barrel": "#eaeaea", "turret_bubble_fill": "#222",
    "turret_bubble_text": "#fff", "pedestal": "#2f2f2f",
    "scroll_handle": "rgba(130, 134, 142, 0.65)", "scroll_bg": "rgba(14, 15, 17, 0.75)"
}
THEME_LIGHT = {
    "bg": "#f1f2f4", "bg_alt": "#ffffff",
    "fg": "#1d2026", "muted_fg": "#6f7682",
    "btn_bg": "rgba(252, 252, 253, 0.96)", "hover_bg": "rgba(240, 242, 246, 0.98)",
    "card_bg": "rgba(255, 255, 255, 0.94)", "card_bg_2": "rgba(249, 250, 252, 0.96)",
    "border": "rgba(0, 0, 0, 0.12)", "accent": "#e54b52",
    "turret_base_fill": "#e6e6e6", "turret_base_outline": "#888",
    "turret_barrel": "#444", "turret_bubble_fill": "#f5f5f5",
    "turret_bubble_text": "#000", "pedestal": "#e0e0e0",
    "scroll_handle": "rgba(122, 128, 138, 0.55)", "scroll_bg": "rgba(232, 234, 238, 0.88)"
}
