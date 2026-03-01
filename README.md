# TurretEye

Aplikacja desktopowa do przeglądania i podstawowej edycji obrazów (PyQt6 + PIL).

## Struktura projektu

- `TurretEye.py` - lekki launcher (kompatybilny punkt startowy).
- `turreteye/config.py` - stałe, tłumaczenia, motywy.
- `turreteye/workers.py` - wątki robocze (np. eksport PDF w tle).
- `turreteye/widgets.py` - własne widgety UI (`ImageViewer`).
- `turreteye/app.py` - główne okno i logika aplikacji (`TurretEyeApp`).
- `turreteye/main.py` - funkcja `main()` uruchamiająca aplikację.
- `requirements.txt` - zależności Pythona.

## Uruchomienie

```bash
pip install -r requirements.txt
python TurretEye.py
```

## Ikony

Interfejs korzysta z open source `Feather Icons` (MIT):
- https://github.com/feathericons/feather
- lokalna kopia: `turreteye/assets/icons/`
