import RPi.GPIO as GPIO
from pathlib import Path

class RotaryEncoder:
    def __init__(self, clk_pin, dt_pin, sw_pin):
        self.clk_pin = clk_pin
        self.dt_pin = dt_pin
        self.sw_pin = sw_pin
        self.clk_last_state = None
        self.callback_cw = None
        self.callback_ccw = None
        self.callback_button = None
        
        GPIO.setup(clk_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(dt_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(sw_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        self.clk_last_state = GPIO.input(clk_pin)
        
        GPIO.add_event_detect(clk_pin, GPIO.BOTH, callback=self._rotation_callback)
        GPIO.add_event_detect(sw_pin, GPIO.FALLING, callback=self._button_callback, bouncetime=300)
        
    def _rotation_callback(self, channel):
        clk_state = GPIO.input(self.clk_pin)
        dt_state = GPIO.input(self.dt_pin)
        
        if clk_state != self.clk_last_state:
            if dt_state != clk_state:
                if self.callback_cw:
                    self.callback_cw()
            else:
                if self.callback_ccw:
                    self.callback_ccw()
                    
        self.clk_last_state = clk_state
        
    def _button_callback(self, channel):
        if self.callback_button:
            self.callback_button()
            
    def set_callbacks(self, callback_cw, callback_ccw, callback_button):
        self.callback_cw = callback_cw
        self.callback_ccw = callback_ccw
        self.callback_button = callback_button

class EncoderManager:
    def __init__(self, volume_pins, sound_select_pins):
        GPIO.setmode(GPIO.BCM)
        
        # Volume encoder
        self.volume_encoder = RotaryEncoder(*volume_pins)
        
        # Sound selection encoder
        self.sound_select_encoder = RotaryEncoder(*sound_select_pins)
        
    def setup_volume_callbacks(self, volume_up, volume_down, volume_mute):
        self.volume_encoder.set_callbacks(volume_up, volume_down, volume_mute)
        
    def setup_sound_select_callbacks(self, next_sound, prev_sound, play_selected):
        self.sound_select_encoder.set_callbacks(next_sound, prev_sound, play_selected)
        
    def cleanup(self):
        GPIO.cleanup()