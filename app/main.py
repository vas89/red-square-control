# -*- coding: utf-8 -*-
"""
Red Square Headset Control — десктопное приложение управления игровыми наушниками.
Стек: Python 3.10+, CustomTkinter, Pillow.
Запуск: python red_square_control.py
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Dict, List, Optional

import customtkinter as ctk
import tkinter as tk
from PIL import Image, ImageDraw, ImageTk

# =============================================================================
#  ЧАСТЬ 1. ДОМЕН И ЛОГИКА (не знает ничего о UI)
# =============================================================================

# Палитра
GRAPHITE = "#121214"
CARD = "#1A1A1F"
CARD_HOVER = "#22222A"
RED_SQUARE = "#FF003C"
CYAN = "#00E5FF"
BLUE = "#2E7BFF"
TEXT = "#EDEDF2"
TEXT_DIM = "#7A7A88"

class Observable:
    """Мини-реализация паттерна наблюдателя: подписка на изменения состояния."""

    def __init__(self) -> None:
        self._subs: Dict[str, List[Callable[[], None]]] = {}

    def subscribe(self, event: str, callback: Callable[[], None]) -> None:
        self._subs.setdefault(event, []).append(callback)

    def emit(self, event: str) -> None:
        for cb in list(self._subs.get(event, [])):
            try:
                cb()
            except Exception:
                pass

@dataclass
class AppState:
    """Единое состояние приложения. UI читает его и перерисовывается по событиям."""
    connected: bool = True
    device_name: str = "Red Square RS-900 Pro"
    battery: int = 78
    charging: bool = False

    volume: int = 60
    mic_gain: int = 50
    mic_muted: bool = False
    noise_cancellation: bool = True
    sidetone: int = 20

    eq_bands: List[float] = field(default_factory=lambda: [0.0] * 10)
    eq_preset: str = "Flat"

    rgb_mode: str = "Статичный"
    rgb_color: str = RED_SQUARE
    rgb_brightness: int = 80

    active_profile: str = "CS2 / Valorant"

EQ_FREQUENCIES = ["32", "64", "125", "250", "500", "1k", "2k", "4k", "8k", "16k"]

EQ_PRESETS: Dict[str, List[float]] = {
    "Flat": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "Gaming": [3, 2, 0, -1, -2, 1, 3, 4, 3, 1],
    "Bass Boost": [8, 7, 5, 3, 1, 0, -1, 0, 1, 2],
    "Cyber-Crystalline Cinema": [2, 1, 0, 2, 4, 5, 4, 2, 3, 5],
}

RGB_MODES = ["Статичный", "Дыхание", "Неоновая волна", "Выключено"]

DEFAULT_PROFILES: Dict[str, dict] = {
    "CS2 / Valorant": {
        "eq_preset": "Gaming",
        "eq_bands": EQ_PRESETS["Gaming"],
        "volume": 72,
        "rgb_mode": "Неоновая волна",
        "rgb_color": "#FF003C",
        "mic_gain": 65,
        "noise_cancellation": True,
    },
    "Музыка": {
        "eq_preset": "Cyber-Crystalline Cinema",
        "eq_bands": EQ_PRESETS["Cyber-Crystalline Cinema"],
        "volume": 55,
        "rgb_mode": "Дыхание",
        "rgb_color": "#00E5FF",
        "mic_gain": 40,
        "noise_cancellation": False,
    },
    "Стелс-хоррор": {
        "eq_preset": "Bass Boost",
        "eq_bands": EQ_PRESETS["Bass Boost"],
        "volume": 88,
        "rgb_mode": "Выключено",
        "rgb_color": "#2E7BFF",
        "mic_gain": 80,
        "noise_cancellation": True,
    },
}

class MockHeadset:
    """
    Заглушка «прошивки» наушников.
    Здесь были бы реальные HID/USB/Bluetooth-вызовы — сейчас всё имитируется.
    """

    def __init__(self) -> None:
        self._connected = True
        self._battery = 78.0

    def is_connected(self) -> bool:
        return self._connected

    def read_battery(self) -> int:
        # Плавное «протекание» заряда, чтобы индикатор жил
        if self._connected and random.random() < 0.05:
            self._battery = max(5.0, self._battery - random.uniform(0.1, 0.4))
        return int(round(self._battery))

    def set_volume(self, value: int) -> None:
        pass  # здесь реальный вызов: device.set_volume(value)

    def set_eq(self, bands: List[float]) -> None:
        pass

    def set_rgb(self, mode: str, color: str, brightness: int) -> None:
        pass

    def set_mic(self, gain: int, muted: bool, anc: bool) -> None:
        pass

    def set_anc(self, enabled: bool) -> None:
        pass

    def toggle_connection(self) -> bool:
        self._connected = not self._connected
        return self._connected

PROFILES_PATH = Path.home() / ".red_square_profiles.json"

class DeviceService:
    """Бизнес-логика: применяет изменения к устройству и сообщает UI об обновлении."""

    def __init__(self, state: AppState, headset: MockHeadset) -> None:
        self.state = state
        self.headset = headset
        self.bus = Observable()
        self.profiles: Dict[str, dict] = self._load_profiles()

    # --- профили ---
    def _load_profiles(self) -> Dict[str, dict]:
        if PROFILES_PATH.exists():
            try:
                data = json.loads(PROFILES_PATH.read_text("utf-8"))
                if isinstance(data, dict) and data:
                    return data
            except Exception:
                pass
        return dict(DEFAULT_PROFILES)

    def _save_profiles(self) -> None:
        try:
            PROFILES_PATH.write_text(
                json.dumps(self.profiles, ensure_ascii=False, indent=2), "utf-8"
            )
        except Exception:
            pass

    def save_current_as_profile(self, name: str) -> None:
        name = name.strip()
        if not name:
            return
        self.profiles[name] = {
            "eq_preset": self.state.eq_preset,
            "eq_bands": list(self.state.eq_bands),
            "volume": self.state.volume,
            "rgb_mode": self.state.rgb_mode,
            "rgb_color": self.state.rgb_color,
            "mic_gain": self.state.mic_gain,
            "noise_cancellation": self.state.noise_cancellation,
        }
        self.state.active_profile = name
        self._save_profiles()
        self.bus.emit("profiles")

    def delete_profile(self, name: str) -> None:
        if name in self.profiles:
            del self.profiles[name]
            self._save_profiles()
            self.bus.emit("profiles")

    def apply_profile(self, name: str) -> None:
        p = self.profiles.get(name)
        if not p:
            return
        s = self.state
        s.eq_preset = p.get("eq_preset", "Flat")
        s.eq_bands = list(p.get("eq_bands", [0] * 10))
        s.volume = int(p.get("volume", 60))
        s.rgb_mode = p.get("rgb_mode", "Статичный")
        s.rgb_color = p.get("rgb_color", RED_SQUARE)
        s.mic_gain = int(p.get("mic_gain", 50))
        s.noise_cancellation = bool(p.get("noise_cancellation", True))
        s.active_profile = name

        self.headset.set_eq(s.eq_bands)
        self.headset.set_volume(s.volume)
        self.headset.set_rgb(s.rgb_mode, s.rgb_color, s.rgb_brightness)
        self.headset.set_mic(s.mic_gain, s.mic_muted, s.noise_cancellation)
        self.bus.emit("all")

    # --- эквалайзер ---
    def set_eq_band(self, index: int, value: float) -> None:
        self.state.eq_bands[index] = round(value, 1)
        self.state.eq_preset = "Custom"
        self.headset.set_eq(self.state.eq_bands)
        self.bus.emit("eq")

    def apply_eq_preset(self, preset: str) -> None:
        if preset not in EQ_PRESETS:
            return
        self.state.eq_preset = preset
        self.state.eq_bands = list(EQ_PRESETS[preset])
        self.headset.set_eq(self.state.eq_bands)
        self.bus.emit("eq")

    # --- громкость / микрофон ---
    def set_volume(self, value: int) -> None:
        self.state.volume = int(value)
        self.headset.set_volume(self.state.volume)
        self.bus.emit("volume")

    def set_mic_gain(self, value: int) -> None:
        self.state.mic_gain = int(value)
        self.headset.set_mic(self.state.mic_gain, self.state.mic_muted,
                             self.state.noise_cancellation)
        self.bus.emit("mic")

    def toggle_mute(self) -> None:
        self.state.mic_muted = not self.state.mic_muted
        self.headset.set_mic(self.state.mic_gain, self.state.mic_muted,
                             self.state.noise_cancellation)
        self.bus.emit("mic")

    def set_anc(self, enabled: bool) -> None:
        self.state.noise_cancellation = bool(enabled)
        self.headset.set_anc(self.state.noise_cancellation)
        self.bus.emit("mic")

    # --- RGB ---
    def set_rgb_mode(self, mode: str) -> None:
        self.state.rgb_mode = mode
        self.headset.set_rgb(mode, self.state.rgb_color, self.state.rgb_brightness)
        self.bus.emit("rgb")

    def set_rgb_color(self, color: str) -> None:
        self.state.rgb_color = color
        self.headset.set_rgb(self.state.rgb_mode, color, self.state.rgb_brightness)
        self.bus.emit("rgb")

    def set_rgb_brightness(self, value: int) -> None:
        self.state.rgb_brightness = int(value)
        self.headset.set_rgb(self.state.rgb_mode, self.state.rgb_color, value)
        self.bus.emit("rgb")

    # --- подключение и заряд ---
    def toggle_connection(self) -> None:
        self.state.connected = self.headset.toggle_connection()
        self.bus.emit("connection")

    def poll_battery(self) -> None:
        new = self.headset.read_battery()
        if new != self.state.battery:
            self.state.battery = new
            self.bus.emit("battery")
# =============================================================================
#  ЧАСТЬ 2. КАСТОМНЫЕ ВИДЖЕТЫ (canvas-рисование, неон, анимация)
# =============================================================================

def hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"

def mix(c1: str, c2: str, t: float) -> str:
    """Линейная интерполяция двух цветов — для плавных переходов."""
    a, b = hex_to_rgb(c1), hex_to_rgb(c2)
    return rgb_to_hex(*(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))

class NeonArcMeter(tk.Canvas):
    """Круговая шкала с неоновой подсветкой (громкость, микрофон)."""

    SIZE = 168

    def __init__(self, master, title: str, accent: str = CYAN, **kw):
        super().__init__(master, width=self.SIZE, height=self.SIZE,
                         bg=CARD, highlightthickness=0, **kw)
        self.title = title
        self.accent = accent
        self.value = 0
        self._anim = 0
        self._draw_arcs()

    def _draw_arcs(self) -> None:
        self.delete("all")
        c, s = self.SIZE / 2, self.SIZE
        pad = 16
        self.create_oval(pad, pad, s - pad, s - pad, outline="#2A2A33", width=10)
        # Подложка под значение
        self.create_arc(pad, pad, s - pad, s - pad, start=90, extent=-359,
                        style="arc", outline="#1F1F26", width=10)
        self._value_arc = self.create_arc(
            pad, pad, s - pad, s - pad, start=90, extent=0,
            style="arc", outline=self.accent, width=10
        )
        self._text = self.create_text(c, c - 6, text="0%", fill=TEXT,
                                      font=("Segoe UI", 22, "bold"))
        self.create_text(c, c + 20, text=self.title, fill=TEXT_DIM,
                         font=("Segoe UI", 9))
        self._update_arc()

    def set_value(self, value: int, animate: bool = True) -> None:
        self.value = max(0, min(100, int(value)))
        if animate:
            self._tween()
        else:
            self._update_arc()

    def _tween(self) -> None:
        # Плавное «догоняние» целевого значения
        current = getattr(self, "_current", 0)
        if current == self.value:
            return
        step = 1 if self.value > current else -1
        self._current = current + step
        self._update_arc(self._current)
        self.after(8, self._tween)

    def _update_arc(self, value: Optional[int] = None) -> None:
        v = self.value if value is None else value
        self.itemconfig(self._value_arc, extent=-3.6 * v)
        self.itemconfig(self._text, text=f"{v}%")

    def set_accent(self, color: str) -> None:
        self.accent = color
        self.itemconfig(self._value_arc, outline=color)

class EqualizerCanvas(tk.Canvas):
    """10-полосный эквалайзер с перетаскиваемыми ползунками."""

    H = 260
    MIN_DB, MAX_DB = -12.0, 12.0

    def __init__(self, master, on_change: Callable[[int, float], None], **kw):
        super().__init__(master, height=self.H, bg=CARD,
                         highlightthickness=0, **kw)
        self.on_change = on_change
        self.bands = [0.0] * 10
        self._drag: Optional[int] = None
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))

    def _geom(self):
        w = max(self.winfo_width(), 200)
        pad = 26
        step = (w - 2 * pad) / 9
        top, bottom = 14, self.H - 28
        return w, pad, step, top, bottom

    def _y_for(self, db: float, top: int, bottom: int) -> float:
        t = (db - self.MIN_DB) / (self.MAX_DB - self.MIN_DB)
        return bottom - t * (bottom - top)

    def _db_for(self, y: float, top: int, bottom: int) -> float:
        t = (bottom - y) / (bottom - top)
        return round(self.MIN_DB + t * (self.MAX_DB - self.MIN_DB), 1)

    def redraw(self) -> None:
        self.delete("all")
        w, pad, step, top, bottom = self._geom()
        cx = [pad + i * step for i in range(10)]

        # Сетка и нулевая линия
        for db in (12, 6, 0, -6, -12):
            y = self._y_for(db, top, bottom)
            color = "#3A3A46" if db == 0 else "#1F1F26"
            self.create_line(pad - 10, y, w - pad + 10, y, fill=color, dash=(2, 4))
            self.create_text(8, y, text=f"{db:+.0f}", fill=TEXT_DIM,
                             font=("Segoe UI", 7), anchor="w")

        for i, db in enumerate(self.bands):
            x = cx[i]
            y = self._y_for(db, top, bottom)
            zero_y = self._y_for(0, top, bottom)
            # Столбик от нуля к текущему значению
            self.create_line(x, zero_y, x, y, fill=CYAN, width=3,
                             capstyle="round")
            # Свечение вокруг ручки
            self.create_oval(x - 11, y - 11, x + 11, y + 11,
                             outline=RED_SQUARE, width=2)
            self.create_oval(x - 5, y - 5, x + 5, y + 5,
                             fill=RED_SQUARE, outline="")
            self.create_text(x, bottom + 16, text=EQ_FREQUENCIES[i],
                             fill=TEXT_DIM, font=("Segoe UI", 8))

    def _on_press(self, event) -> None:
        w, pad, step, top, bottom = self._geom()
        idx = int(round((event.x - pad) / step))
        if 0 <= idx <= 9 and top - 20 <= event.y <= bottom + 10:
            self._drag = idx
            self._apply(event)

    def _on_drag(self, event) -> None:
        if self._drag is not None:
            self._apply(event)

    def _apply(self, event) -> None:
        _, _, _, top, bottom = self._geom()
        db = self._db_for(event.y, top, bottom)
        db = max(self.MIN_DB, min(self.MAX_DB, db))
        if self.bands[self._drag] != db:
            self.bands[self._drag] = db
            self.redraw()
            self.on_change(self._drag, db)

    def set_bands(self, bands: List[float]) -> None:
        self.bands = list(bands)
        self.redraw()

class NeonGauge(tk.Canvas):
    """Индикатор уровня сигнала с бегущими столбиками (анимация)."""

    def __init__(self, master, bars: int = 28, accent: str = CYAN, **kw):
        super().__init__(master, height=70, bg=CARD, highlightthickness=0, **kw)
        self.bars = bars
        self.accent_color = accent
        self.levels = [0.0] * bars
        self.running = True
        self.bind("<Configure>", lambda e: self._tick())

    def _tick(self) -> None:
        if not self.running:
            return
        w = max(self.winfo_width(), 10)
        self.delete("all")
        bw = max(3, (w - self.bars * 4) / self.bars)
        for i, lvl in enumerate(self.levels):
            # Целевой уровень — псевдослучайный «живой» сигнал
            target = random.uniform(0.15, 1.0)
            self.levels[i] = self.levels[i] * 0.6 + target * 0.4
            h = lvl * 46
            x0 = i * (bw + 4) + 2
            col = self.accent_color if lvl > 0.45 else BLUE
            self.create_rectangle(x0, 60 - h, x0 + bw, 60,
                                  fill=col, outline="")
        self.after(90, self._tick)

    def set_accent(self, color: str) -> None:
        self.accent_color = color

class ColorSwatch(tk.Canvas):
    """Кружок-палитра с неоновым ободком."""

    def __init__(self, master, color: str, on_pick: Callable[[str], None], **kw):
        super().__init__(master, width=38, height=38, bg=CARD,
                         highlightthickness=0, cursor="hand2", **kw)
        self.color = color
        self.on_pick = on_pick
        self.selected = False
        self._paint()
        self.bind("<Button-1>", lambda e: self.on_pick(self.color))

    def _paint(self) -> None:
        self.delete("all")
        ring = TEXT if self.selected else "#32323C"
        self.create_oval(2, 2, 36, 36, outline=ring, width=2)
        self.create_oval(7, 7, 31, 31, fill=self.color, outline="")

    def set_selected(self, flag: bool) -> None:
        self.selected = flag
        self._paint()

class HeadsetPreview(tk.Canvas):
    """Мини-превью наушников с анимированной RGB-подсветкой."""

    def __init__(self, master, **kw):
        super().__init__(master, width=320, height=170, bg=CARD,
                         highlightthickness=0, **kw)
        self.mode = "Статичный"
        self.color = RED_SQUARE
        self.brightness = 80
        self._t = 0.0
        self._animate()

    def config_light(self, mode: str, color: str, brightness: int) -> None:
        self.mode = mode
        self.color = color
        self.brightness = brightness

    def _animate(self) -> None:
        self._t += 0.05
        self.delete("all")
        cx, cy = 160, 85
        active = self.mode != "Выключено"
        glow = (self.brightness / 100) if active else 0.0

        if self.mode == "Дыхание":
            k = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(self._t * 1.6))
        elif self.mode == "Неоновая волна":
            k = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self._t * 3.0))
        else:
            k = 1.0
        intensity = glow * k

        # Дуга и амбушюры
        self.create_arc(cx - 60, cy - 72, cx + 60, cy + 40, start=0, extent=180,
                        style="arc", outline="#3A3A46", width=9)
        for side in (-1, 1):
            x = cx + side * 62
            outline = mix(CARD, self.color, intensity) if active else "#3A3A46"
            self.create_oval(x - 26, cy - 8, x + 26, cy + 52,
                             outline=outline, width=4)
            self.create_oval(x - 16, cy + 2, x + 16, cy + 42,
                             outline=mix(CARD, self.color, intensity * 0.7)
                             if active else "#2A2A33", width=2)
        # Свечение под наушниками
        if active:
            for i in range(3):
                pad = 90 + i * 17
                col = mix(CARD, self.color, intensity * (0.30 - i * 0.08))
                self.create_oval(cx - pad, cy + 34 - i * 6, cx + pad, cy + 60 + i * 4,
                                 outline=col, width=2)
        self.after(70, self._animate)

class StatusPill(ctk.CTkFrame):
    """Статус подключения с пульсирующей неоновой точкой."""

    def __init__(self, master, service: DeviceService, **kw):
        super().__init__(master, fg_color=CARD, corner_radius=16, **kw)
        self.service = service
        self.dot = tk.Canvas(self, width=22, height=22, bg=CARD,
                             highlightthickness=0)
        self.dot.pack(side="left", padx=(14, 4), pady=8)
        self.label = ctk.CTkLabel(self, text="", font=("Segoe UI", 12, "bold"),
                                  text_color=TEXT)
        self.label.pack(side="left", padx=(0, 14))
        self._phase = 0
        self._pulse()
        self._refresh()
        service.bus.subscribe("connection", self._refresh)

    def _refresh(self) -> None:
        on = self.service.state.connected
        self.label.configure(
            text="ПОДКЛЮЧЕНО" if on else "НЕТ СВЯЗИ",
            text_color=CYAN if on else RED_SQUARE,
        )

    def _pulse(self) -> None:
        self.dot.delete("all")
        on = self.service.state.connected
        col = CYAN if on else RED_SQUARE
        self._phase = (self._phase + 0.18) % (2 * math.pi)
        r = 4 + 2.2 * (0.5 + 0.5 * math.sin(self._phase))
        self.dot.create_oval(11 - r - 4, 11 - r - 4, 11 + r + 4, 11 + r + 4,
                             outline=mix(CARD, col, 0.35), width=1)
        self.dot.create_oval(11 - r, 11 - r, 11 + r, 11 + r, fill=col,
                             outline="")
        self.after(60, self._pulse)
# =============================================================================
#  ЧАСТЬ 3. ЭКРАНЫ
# =============================================================================

def card(parent, **kw) -> ctk.CTkFrame:
    """Карточка с полупрозрачным фоном и скруглением."""
    return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=18, **kw)

class BaseTab(ctk.CTkFrame):
    def __init__(self, master, service: DeviceService):
        super().__init__(master, fg_color="transparent")
        self.service = service
        self.build()

    def build(self) -> ...:
        raise NotImplementedError

    def refresh(self) -> None:
        pass

class DashboardTab(BaseTab):
    """Главный экран: статус, заряд, громкость, живой эквалайзер."""

    def build(self) -> None:
        s = self.service.state
        self.grid_columnconfigure((0, 1), weight=1, uniform="d")
        self.grid_rowconfigure(1, weight=1)

        hero = card(self)
        hero.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
        hero.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(hero, fg_color="transparent")
        left.grid(row=0, column=0, padx=20, pady=18, sticky="nw")
        ctk.CTkLabel(left, text="RED SQUARE", font=("Segoe UI", 11, "bold"),
                     text_color=RED_SQUARE).pack(anchor="w")
        ctk.CTkLabel(left, text=s.device_name, font=("Segoe UI", 26, "bold"),
                     text_color=TEXT).pack(anchor="w", pady=(2, 10))
        self.pill = StatusPill(left, self.service)
        self.pill.pack(anchor="w")

        self.preview = HeadsetPreview(hero)
        self.preview.grid(row=0, column=1, padx=16, pady=10, sticky="e")
        self.preview.config_light(s.rgb_mode, s.rgb_color, s.rgb_brightness)

        # Заряд
        bat = card(self)
        bat.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        ctk.CTkLabel(bat, text="ЗАРЯД БАТАРЕИ", font=("Segoe UI", 10, "bold"),
                     text_color=TEXT_DIM).pack(anchor="w", padx=20, pady=(18, 4))
        self.bat_value = ctk.CTkLabel(bat, text="", font=("Segoe UI", 40, "bold"),
                                      text_color=CYAN)
        self.bat_value.pack(anchor="w", padx=20)
        self.bat_bar = ctk.CTkProgressBar(bat, height=10, corner_radius=6,
                                          progress_color=RED_SQUARE,
                                          fg_color="#26262E")
        self.bat_bar.pack(fill="x", padx=20, pady=(8, 16))
        ctk.CTkButton(bat, text="Симулировать отключение",
                      fg_color="transparent", border_width=1,
                      border_color="#33333D", text_color=TEXT_DIM,
                      hover_color=CARD_HOVER, corner_radius=10,
                      command=self.service.toggle_connection
                      ).pack(anchor="w", padx=20, pady=(0, 18))

        # Громкость
        vol = card(self)
        vol.grid(row=1, column=1, sticky="nsew", padx=6, pady=6)
        ctk.CTkLabel(vol, text="ГРОМКОСТЬ", font=("Segoe UI", 10, "bold"),
                     text_color=TEXT_DIM).pack(anchor="w", padx=20, pady=(18, 0))
        self.vol_meter = NeonArcMeter(vol, "MASTER", RED_SQUARE)
        self.vol_meter.pack(pady=(4, 4))
        self.vol_meter._current = s.volume
        self.vol_meter.set_value(s.volume, animate=False)
        ctk.CTkSlider(vol, from_=0, to=100, number_of_steps=100,
                      progress_color=RED_SQUARE, button_color=RED_SQUARE,
                      button_hover_color="#FF4D75", fg_color="#26262E",
                      command=lambda v: self.service.set_volume(int(v))
                      ).pack(fill="x", padx=20, pady=(0, 18))

        # Эквалайзер-«жизнь»
        wave = card(self)
        wave.grid(row=2, column=0, columnspan=2, sticky="ew", padx=6, pady=6)
        ctk.CTkLabel(wave, text="ВХОДЯЩИЙ СИГНАЛ", font=("Segoe UI", 10, "bold"),
                     text_color=TEXT_DIM).pack(anchor="w", padx=20, pady=(14, 2))
        self.wave = NeonGauge(wave, bars=40, accent=RED_SQUARE)
        self.wave.pack(fill="x", padx=16, pady=(0, 14))

        for ev, fn in (("battery", self.refresh), ("volume", self._sync_volume),
                       ("connection", self.refresh), ("rgb", self._sync_rgb),
                       ("all", self.refresh)):
            self.service.bus.subscribe(ev, fn)
        self.refresh()

    def _sync_volume(self) -> None:
        v = self.service.state.volume
        self.vol_meter.set_value(v)

    def _sync_rgb(self) -> None:
        s = self.service.state
        self.preview.config_light(s.rgb_mode, s.rgb_color, s.rgb_brightness)

    def refresh(self) -> None:
        s = self.service.state
        self.bat_value.configure(text=f"{s.battery}%")
        self.bat_bar.set(s.battery / 100)
        col = RED_SQUARE if s.battery < 20 else CYAN
        self.bat_value.configure(text_color=col)
        self.bat_bar.configure(progress_color=col)
        self._sync_volume()
        self._sync_rgb()
        if s.connected:
            self.wave.running = True
        else:
            self.wave.running = False

class EqualizerTab(BaseTab):
    def build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        s = self.service.state

        top = card(self)
        top.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        ctk.CTkLabel(top, text="ПРЕСЕТЫ", font=("Segoe UI", 10, "bold"),
                     text_color=TEXT_DIM).pack(anchor="w", padx=20, pady=(14, 6))
        row = ctk.CTkFrame(top, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 14))
        self.buttons = {}
        for name in EQ_PRESETS:
            b = ctk.CTkButton(
                row, text=name, height=36, corner_radius=12,
                fg_color="#22222A", hover_color="#2C2C36",
                text_color=TEXT, font=("Segoe UI", 12),
                command=lambda n=name: self.service.apply_eq_preset(n),
            )
            b.pack(side="left", padx=4, expand=True, fill="x")
            self.buttons[name] = b

        body = card(self)
        body.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        head = ctk.CTkFrame(body, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(14, 0))
        ctk.CTkLabel(head, text="10-ПОЛОСНЫЙ ЭКВАЛАЙЗЕР", font=("Segoe UI", 10, "bold"),
                     text_color=TEXT_DIM).pack(side="left")
        self.preset_label = ctk.CTkLabel(head, text=s.eq_preset,
                                         font=("Segoe UI", 11, "bold"),
                                         text_color=CYAN)
        self.preset_label.pack(side="right")

        self.canvas = EqualizerCanvas(body, on_change=self.service.set_eq_band)
        self.canvas.pack(fill="both", expand=True, padx=14, pady=(8, 6))
        self.canvas.set_bands(s.eq_bands)

        ctk.CTkButton(body, text="Сбросить в 0 dB", height=34, corner_radius=10,
                      fg_color="transparent", border_width=1,
                      border_color="#33333D", text_color=TEXT_DIM,
                      hover_color=CARD_HOVER,
                      command=lambda: self.service.apply_eq_preset("Flat")
                      ).pack(anchor="e", padx=20, pady=(0, 16))

        self.service.bus.subscribe("eq", self.refresh)
        self.service.bus.subscribe("all", self.refresh)
        self.refresh()

    def refresh(self) -> None:
        s = self.service.state
        self.canvas.set_bands(s.eq_bands)
        self.preset_label.configure(text=s.eq_preset)
        for name, b in self.buttons.items():
            if name == s.eq_preset:
                b.configure(fg_color=RED_SQUARE, text_color="#FFFFFF",
                            hover_color="#D40033")
            else:
                b.configure(fg_color="#22222A", text_color=TEXT,
                            hover_color="#2C2C36")

class RGBTab(BaseTab):
    PALETTE = ["#FF003C", "#00E5FF", "#2E7BFF", "#9D4BFF",
               "#00FF9D", "#FFD400", "#FF6A00", "#FFFFFF"]

    def build(self) -> None:
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)
        s = self.service.state

        left = card(self)
        left.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        ctk.CTkLabel(left, text="РЕЖИМ ПОДСВЕТКИ", font=("Segoe UI", 10, "bold"),
                     text_color=TEXT_DIM).pack(anchor="w", padx=20, pady=(16, 6))
        self.mode_buttons = {}
        for mode in RGB_MODES:
            b = ctk.CTkButton(left, text=mode, height=40, corner_radius=12,
                              anchor="w", fg_color="#22222A", hover_color="#2C2C36",
                              text_color=TEXT, font=("Segoe UI", 12),
                              command=lambda m=mode: self.service.set_rgb_mode(m))
            b.pack(fill="x", padx=20, pady=3)
            self.mode_buttons[mode] = b

        ctk.CTkLabel(left, text="ЦВЕТ", font=("Segoe UI", 10, "bold"),
                     text_color=TEXT_DIM).pack(anchor="w", padx=20, pady=(16, 6))
        pal = ctk.CTkFrame(left, fg_color="transparent")
        pal.pack(anchor="w", padx=16)
        self.swatches = []
        for i, c in enumerate(self.PALETTE):
            sw = ColorSwatch(pal, c, self.service.set_rgb_color)
            sw.grid(row=i // 4, column=i % 4, padx=3, pady=3)
            self.swatches.append(sw)

        ctk.CTkLabel(left, text="ЯРКОСТЬ", font=("Segoe UI", 10, "bold"),
                     text_color=TEXT_DIM).pack(anchor="w", padx=20, pady=(16, 0))
        self.bright_label = ctk.CTkLabel(left, text="", font=("Segoe UI", 12, "bold"),
                                         text_color=CYAN)
        self.bright_label.pack(anchor="w", padx=20)
        ctk.CTkSlider(left, from_=0, to=100, number_of_steps=100,
                      progress_color=RED_SQUARE, button_color=RED_SQUARE,
                      button_hover_color="#FF4D75", fg_color="#26262E",
                      command=lambda v: self.service.set_rgb_brightness(int(v))
                      ).pack(fill="x", padx=20, pady=(4, 18))

        right = card(self)
        right.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        ctk.CTkLabel(right, text="ЖИВОЕ ПРЕВЬЮ", font=("Segoe UI", 10, "bold"),
                     text_color=TEXT_DIM).pack(anchor="w", padx=18, pady=(16, 4))
        self.preview = HeadsetPreview(right)
        self.preview.pack(expand=True)
        self.info = ctk.CTkLabel(right, text="", font=("Segoe UI", 11),
                                 text_color=TEXT_DIM)
        self.info.pack(pady=(0, 16))

        self.service.bus.subscribe("rgb", self.refresh)
        self.service.bus.subscribe("all", self.refresh)
        self.refresh()

    def refresh(self) -> None:
        s = self.service.state
        for mode, b in self.mode_buttons.items():
            if mode == s.rgb_mode:
                b.configure(fg_color=RED_SQUARE, text_color="#FFFFFF",
                            hover_color="#D40033")
            else:
                b.configure(fg_color="#22222A", text_color=TEXT,
                            hover_color="#2C2C36")
        for sw in self.swatches:
            sw.set_selected(sw.color.upper() == s.rgb_color.upper())
        self.bright_label.configure(text=f"{s.rgb_brightness}%")
        self.preview.config_light(s.rgb_mode, s.rgb_color, s.rgb_brightness)
        self.info.configure(text=f"{s.rgb_mode} · {s.rgb_color}")

class MicTab(BaseTab):
    def build(self) -> None:
        self.grid_columnconfigure((0, 1), weight=1)
        self.grid_rowconfigure(0, weight=1)
        s = self.service.state

        left = card(self)
        left.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        ctk.CTkLabel(left, text="ЧУВСТВИТЕЛЬНОСТЬ", font=("Segoe UI", 10, "bold"),
                     text_color=TEXT_DIM).pack(anchor="w", padx=20, pady=(16, 0))
        self.meter = NeonArcMeter(left, "MIC GAIN", CYAN)
        self.meter.pack(pady=6)
        self.meter._current = s.mic_gain
        self.meter.set_value(s.mic_gain, animate=False)
        ctk.CTkSlider(left, from_=0, to=100, number_of_steps=100,
                      progress_color=CYAN, button_color=CYAN,
                      button_hover_color="#66F0FF", fg_color="#26262E",
                      command=lambda v: self.service.set_mic_gain(int(v))
                      ).pack(fill="x", padx=20, pady=(0, 12))

        self.mute_btn = ctk.CTkButton(left, text="MUTE", height=46,
                                      corner_radius=14, font=("Segoe UI", 14, "bold"),
                                      command=self.service.toggle_mute)
        self.mute_btn.pack(fill="x", padx=20, pady=(0, 18))

        right = card(self)
        right.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        ctk.CTkLabel(right, text="AI NOISE CANCELLATION",
                     font=("Segoe UI", 10, "bold"),
                     text_color=TEXT_DIM).pack(anchor="w", padx=20, pady=(16, 4))
        self.anc_switch = ctk.CTkSwitch(right, text="", onvalue=True, offvalue=False,
                                        progress_color=CYAN, button_color=CYAN,
                                        command=self._anc_changed)
        self.anc_switch.pack(anchor="w", padx=20, pady=(4, 3))
        self.anc_status = ctk.CTkLabel(right, text="", font=("Segoe UI", 13, "bold"))
        self.anc_status.pack(anchor="w", padx=20, pady=(0, 14))

        ctk.CTkLabel(right, text="УРОВЕНЬ СИГНАЛА", font=("Segoe UI", 10, "bold"),
                     text_color=TEXT_DIM).pack(anchor="w", padx=20, pady=(6, 2))
        self.wave = NeonGauge(right, bars=26, accent=CYAN)
        self.wave.pack(fill="x", padx=14, pady=(0, 10))
        ctk.CTkLabel(right,
                     text="Шумоподавление фильтрует фон клавиатуры, кулеров\n"
                          "и вентиляции в реальном времени (демо-режим).",
                     font=("Segoe UI", 10), text_color=TEXT_DIM,
                     justify="left").pack(anchor="w", padx=20, pady=(0, 16))

        self.service.bus.subscribe("mic", self.refresh)
        self.service.bus.subscribe("all", self.refresh)
        self.refresh()

    def _anc_changed(self) -> None:
        self.service.set_anc(bool(self.anc_switch.get()))

    def refresh(self) -> None:
        s = self.service.state
        self.anc_switch.select() if s.noise_cancellation else self.anc_switch.deselect()
        self.anc_status.configure(
            text="АКТИВНО" if s.noise_cancellation else "ОТКЛЮЧЕНО",
            text_color=CYAN if s.noise_cancellation else TEXT_DIM,
        )
        if s.mic_muted:
            self.mute_btn.configure(text="МИКРОФОН ВЫКЛЮЧЕН",
                                    fg_color=RED_SQUARE, hover_color="#D40033",
                                    text_color="#FFFFFF")
            self.meter.set_value(0)
            self.wave.running = False
        else:
            self.mute_btn.configure(text="MUTE", fg_color="#22222A",
                                    hover_color="#2C2C36", text_color=TEXT)
            self.meter._current = s.mic_gain
            self.meter.set_value(s.mic_gain, animate=False)
            self.wave.running = True

class ProfilesTab(BaseTab):
    def build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = card(self)
        top.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        ctk.CTkLabel(top, text="НОВЫЙ ПРОФИЛЬ", font=("Segoe UI", 10, "bold"),
                     text_color=TEXT_DIM).pack(anchor="w", padx=20, pady=(14, 6))
        row = ctk.CTkFrame(top, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 16))
        self.name_entry = ctk.CTkEntry(row, height=38, corner_radius=12,
                                       placeholder_text="Имя профиля…",
                                       fg_color="#22222A", border_width=1,
                                       border_color="#33333D", text_color=TEXT)
        self.name_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(row, text="Сохранить текущие настройки", height=38,
                      corner_radius=12, fg_color=RED_SQUARE, hover_color="#D40033",
                      font=("Segoe UI", 12, "bold"),
                      command=self._save).pack(side="left")

        self.list_frame = card(self)
        self.list_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        ctk.CTkLabel(self.list_frame, text="СОХРАНЁННЫЕ ПРОФИЛИ",
                     font=("Segoe UI", 10, "bold"),
                     text_color=TEXT_DIM).pack(anchor="w", padx=20, pady=(16, 8))
        self.items = ctk.CTkScrollableFrame(self.list_frame, fg_color="transparent")
        self.items.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        self.service.bus.subscribe("profiles", self.refresh)
        self.service.bus.subscribe("all", self.refresh)
        self._save_ref = self.service
        self.refresh()

    def _save(self) -> None:
        name = self.name_entry.get().strip()
        if name:
            self.service.save_current_as_profile(name)
            self.name_entry.delete(0, "end")

    def refresh(self) -> None:
        for w in self.items.winfo_children():
            w.destroy()
        active = self.service.state.active_profile
        for name, data in self.service.profiles.items():
            row = ctk.CTkFrame(self.items, fg_color="#202027", corner_radius=14)
            row.pack(fill="x", pady=4)
            is_active = name == active
            txt = ctk.CTkFrame(row, fg_color="transparent")
            txt.pack(side="left", padx=16, pady=10)
            ctk.CTkLabel(txt, text=name, font=("Segoe UI", 13, "bold"),
                         text_color=RED_SQUARE if is_active else TEXT
                         ).pack(anchor="w")
            ctk.CTkLabel(txt,
                         text=f"{data.get('eq_preset', '—')} · vol {data.get('volume', '—')}%"
                              f" · {data.get('rgb_mode', '—')}",
                         font=("Segoe UI", 10), text_color=TEXT_DIM).pack(anchor="w")
            ctk.CTkButton(row, text="Удалить", width=76, height=30,
                          corner_radius=10, fg_color="transparent",
                          border_width=1, border_color="#3A2027",
                          text_color="#FF6A88", hover_color="#2A1418",
                          command=lambda n=name: self.service.delete_profile(n)
                          ).pack(side="right", padx=(4, 14))
            ctk.CTkButton(row, text="Загрузить", width=96, height=30,
                          corner_radius=10,
                          fg_color=RED_SQUARE if not is_active else "#2A2A33",
                          hover_color="#D40033",
                          text_color="#FFFFFF" if not is_active else TEXT_DIM,
                          command=lambda n=name: self.service.apply_profile(n)
                          ).pack(side="right", padx=4)
# =============================================================================
#  ЧАСТЬ 4. ГЛАВНОЕ ОКНО
# =============================================================================

class MainWindow(ctk.CTk):
    TABS = [
        ("Главная", DashboardTab),
        ("Эквалайзер", EqualizerTab),
        ("Подсветка RGB", RGBTab),
        ("Микрофон", MicTab),
        ("Профили", ProfilesTab),
    ]

    def __init__(self, service: DeviceService):
        super().__init__(fg_color=GRAPHITE)
        self.service = service
        self.title("Red Square — Headset Control")
        self.geometry("1100x760")
        self.minsize(900, 640)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Верхняя панель
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 6))
        header.grid_columnconfigure(1, weight=1)
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(title_box, text="RED SQUARE",
                     font=("Segoe UI", 22, "bold"),
                     text_color=RED_SQUARE).pack(side="left")
        ctk.CTkLabel(title_box, text="  CONTROL CENTER",
                     font=("Segoe UI", 22), text_color=TEXT_DIM).pack(side="left")
        StatusPill(header, self.service).grid(row=0, column=2, sticky="e")

        # Навигация
        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 4))
        self.tab_buttons = {}
        for i, (label, _) in enumerate(self.TABS):
            b = ctk.CTkButton(nav, text=label, height=36, corner_radius=12,
                              fg_color="transparent", text_color=TEXT_DIM,
                              hover_color="#1E1E24", font=("Segoe UI", 12, "bold"),
                              command=lambda i=i: self.show_tab(i))
            b.pack(side="left", padx=(0, 6))
            self.tab_buttons[i] = b
        ctk.CTkFrame(nav, height=1, fg_color="#26262E").pack(
            side="left", fill="x", expand=True, padx=(8, 0))

        # Контейнер экранов
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.tabs = []
        for _, cls in self.TABS:
            tab = cls(self.body, self.service)
            tab.grid(row=0, column=0, sticky="nsew")
            self.tabs.append(tab)
        self.current = -1
        self.show_tab(0)

        # Опрос заряда
        self._poll()

    def show_tab(self, index: int) -> None:
        if index == self.current:
            return
        self.current = index
        self.tabs[index].tkraise()
        for i, b in self.tab_buttons.items():
            if i == index:
                b.configure(fg_color="#22222A", text_color=RED_SQUARE)
            else:
                b.configure(fg_color="transparent", text_color=TEXT_DIM)

    def _poll(self) -> None:
        self.service.poll_battery()
        self.after(3000, self._poll)

def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    state = AppState()
    headset = MockHeadset()
    service = DeviceService(state, headset)
    app = MainWindow(service)
    app.mainloop()

if __name__ == "__main__":
    main()
