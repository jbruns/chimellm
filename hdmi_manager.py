import vlc
import time
from pathlib import Path
from vcgencmd import Vcgencmd

class HDMIManager:
    def __init__(self, framebuffer):
        self.framebuffer = framebuffer
        self.player = None
        self.is_display_on = False
        self.vcgencmd = Vcgencmd()
        
    def turn_on_display(self):
        if not self.is_display_on:
            try:
                self.vcgencmd.display_power(1)
                self.is_display_on = True
                time.sleep(1)  # Wait for display to initialize
            except Exception as e:
                print(f"Warning: Could not enable display: {e}")
            
    def turn_off_display(self):
        if self.is_display_on:
            if self.player:
                self.stop_video()
            try:
                self.vcgencmd.display_power(0)
            except Exception as e:
                print(f"Warning: Could not disable display: {e}")
            self.is_display_on = False
            
    def play_video(self, url):
        self.turn_on_display()
        if self.player:
            self.player.stop()
            
        instance = vlc.Instance()
        self.player = instance.media_player_new()
        media = instance.media_new(url)
        self.player.set_media(media)
        
        # Configure VLC for framebuffer output
        self.player.set_mrl("--vout=fb")
        self.player.set_options(f"--fb-device={self.framebuffer}")
            
        self.player.play()
        
    def stop_video(self):
        if self.player:
            self.player.stop()
            self.player = None