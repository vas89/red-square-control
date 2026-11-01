import os
import sys
import json
import threading
import time
from abc import ABC, abstractmethod
import customtkinter as ctk
from PIL import Image, ImageDraw
try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
except ImportError:
    pass

class AudioBackend:
    def __init__(self):
        self.volume_interface = None
        self.microphone_interface = None
        if sys.platform == "win32":
            self._init_windows_audio()
    def _init_windows_audio(self):
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self.volume_interface = cast(interface, POINTER(IAudioEndpointVolume))
            microphone = AudioUtilities.GetMicrophone()
            mic_interface = microphone.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self.microphone_interface = cast(mic_interface, POINTER(IAudioEndpointVolume))
        except Exception as e:
            print(f"Audio error: {e}")
    def get_volume(self) -> int:
        if self.volume_interface:
            try:
                return int(self.volume_interface.GetMasterVolumeLevelScalar() * 100)
            except:
                return 50
        return 50
    def set_volume(self, value: int):
        if self.volume_interface:
            try:
                self.volume_interface.SetMasterVolumeLevelScalar(value / 100.0, None)
            except:
                pass
    def get_mic_mute(self) -> bool:
        if self.microphone_interface:
            try:
                return bool(self.microphone_interface.GetMute())
            except:
                return False
        return False
    def set_mic_mute(self, state: bool):
        if self.microphone_interface:
            try:
                self.microphone_interface.SetMute(int(state), None)
            except:
                pass

class VendorBridge:
    def __init__(self):
        self.connected = True
    def set_rgb_mode(self, mode_id: int, color_hex: str, brightness: int):
        print(f"[VendorBridge] RGB Mode: {mode_id}, Color: {color_hex}")
    def get_battery_level(self) -> int:
        return 100

class AppState:
    def __init__(self):
        self.audio = AudioBackend()
        self.hw = VendorBridge()
        self.listeners = []
        self.current_rgb_mode = 0
        self.current_rgb_color = "#FF003C"
        self.rgb_brightness = 80
        self.profiles_file = os.path.expanduser("~/.red_square_profiles.json")
        self.profiles = self.load_profiles()
    def subscribe(self, callback):
        self.listeners.append(callback)
    def notify(self):
        for callback in self.listeners:
            try:
                callback()
            except Exception as e:
                print(f"Listener error: {e}")
    def update_rgb(self, mode, color, brightness):
        self.current_rgb_mode = mode
        self.current_rgb_color = color
        self.rgb_brightness = brightness
        self.hw.set_rgb_mode(mode, color, brightness)
        self.notify()
    def load_profiles(self):
        if os.path.exists(self.profiles_file):
            try:
                with open(self.profiles_file, "r") as f:
                    return json.load(f)
            except:
                return {}
        return {"Gaming": {"vol": 80, "mute": False}, "Music": {"vol": 40, "mute": False}}

class MainApplication(ctk.CTk):
    def __init__(self, state_object: AppState):
        super().__init__()
        self.state_obj = state_object
        self.title("RED SQUARE - Quantum Control v1.5")
        self.geometry("900x600")
        self.minsize(850, 550)
        ctk.set_appearance_mode("dark")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.menu_frame = ctk.CTkFrame(self, width=200, fg_color="#121214", border_color="#FF003C", border_width=1)
        self.menu_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.logo_label = ctk.CTkLabel(self.menu_frame, text="RED SQUARE", font=ctk.CTkFont(size=20, weight="bold"), text_color="#FF003C")
        self.logo_label.pack(pady=20)
        self.content_frame = ctk.CTkFrame(self, fg_color="#18181C")
        self.content_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.screen_main = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.screen_rgb = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.create_main_screen()
        self.create_rgb_screen()
        self.btn_main = ctk.CTkButton(self.menu_frame, text="Аудио и Звук", fg_color="#FF003C", hover_color="#C0002D", command=self.show_main)
        self.btn_main.pack(pady=10, padx=20, fill="x")
        self.btn_rgb = ctk.CTkButton(self.menu_frame, text="RGB Подсветка", fg_color="#222", hover_color="#333", command=self.show_rgb)
        self.btn_rgb.pack(pady=10, padx=20, fill="x")
        self.show_main()
        self.state_obj.subscribe(self.on_state_changed)
        self.run_audio_updater()
    def create_main_screen(self):
        lbl = ctk.CTkLabel(self.screen_main, text="Управление звуком Windows", font=ctk.CTkFont(size=16, weight="bold"), text_color="#00F0FF")
        lbl.pack(pady=20)
        self.vol_slider = ctk.CTkSlider(self.screen_main, from_=0, to=100, button_color="#FF003C", progress_color="#FF003C", command=self.on_slider_move)
        self.vol_slider.set(self.state_obj.audio.get_volume())
        self.vol_slider.pack(pady=20, padx=50, fill="x")
        self.vol_label = ctk.CTkLabel(self.screen_main, text=f"Громкость: {int(self.vol_slider.get())}%", text_color="#FFF")
        self.vol_label.pack()
        self.btn_mute = ctk.CTkButton(self.screen_main, text="Вкл / Выкл микрофон", fg_color="#222", command=self.toggle_mute)
        self.btn_mute.pack(pady=30)
        self.mic_status = ctk.CTkLabel(self.screen_main, text="Микрофон активен", text_color="#00FF66")
        self.mic_status.pack()
    def create_rgb_screen(self):
        lbl = ctk.CTkLabel(self.screen_rgb, text="Неоновая Подсветка", font=ctk.CTkFont(size=16, weight="bold"), text_color="#FF003C")
        lbl.pack(pady=20)
        info_lbl = ctk.CTkLabel(self.screen_rgb, text="[Подсветка и батарея: режим эмуляции]", text_color="#777")
        info_lbl.pack(pady=10)
        btn_neon = ctk.CTkButton(self.screen_rgb, text="Включить Кибер-Волну", fg_color="#FF003C", command=lambda: self.state_obj.update_rgb(1, "#FF003C", 100))
        btn_neon.pack(pady=10)
    def show_main(self):
        self.screen_rgb.grid_forget()
        self.screen_main.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.btn_main.configure(fg_color="#FF003C")
        self.btn_rgb.configure(fg_color="#222")
    def show_rgb(self):
        self.screen_main.grid_forget()
        self.screen_rgb.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.btn_main.configure(fg_color="#222")
        self.btn_rgb.configure(fg_color="#FF003C")
    def on_slider_move(self, value):
        self.state_obj.audio.set_volume(int(value))
        self.vol_label.configure(text=f"Громкость: {int(value)}%")
    def toggle_mute(self):
        current_state = self.state_obj.audio.get_mic_mute()
        self.state_obj.audio.set_mic_mute(not current_state)
        self.on_state_changed()
    def on_state_changed(self):
        is_muted = self.state_obj.audio.get_mic_mute()
        if is_muted:
            self.mic_status.configure(text="Микрофон ОТКЛЮЧЕН (MUTE)", text_color="#FF003C")
            self.btn_mute.configure(fg_color="#FF003C")
        else:
            self.mic_status.configure(text="Микрофон: Работает", text_color="#00FF66")
            self.btn_mute.configure(fg_color="#222")
    def run_audio_updater(self):
        try:
            current_vol = self.state_obj.audio.get_volume()
            self.vol_slider.set(current_vol)
            self.vol_label.configure(text=f"Громкость: {current_vol}%")
        except:
            pass
        self.after(500, self.run_audio_updater)

if __name__ == "__main__":
    global_state = AppState()
    application = MainApplication(global_state)
    application.mainloop()
