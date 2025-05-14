import RPi.GPIO as GPIO
from pathlib import Path

class RotaryEncoder:
    def __init__(self, clk_pin, dt_pin, sw_pin):
        """Initialize a rotary encoder with GPIO pins.
        
        Args:
            clk_pin (int): GPIO pin number for the clock signal
            dt_pin (int): GPIO pin number for the data signal
            sw_pin (int): GPIO pin number for the switch/button"""
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
        """Internal callback for handling rotary encoder rotation.
        Determines rotation direction and calls appropriate callback.
        
        Args:
            channel (int): GPIO channel that triggered the event"""
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
        """Internal callback for handling button press events.
        
        Args:
            channel (int): GPIO channel that triggered the event"""
        if self.callback_button:
            self.callback_button()
            
    def set_callbacks(self, callback_cw, callback_ccw, callback_button):
        """Set the callback functions for encoder events.
        
        Args:
            callback_cw (callable): Function to call on clockwise rotation
            callback_ccw (callable): Function to call on counter-clockwise rotation
            callback_button (callable): Function to call on button press"""
        self.callback_cw = callback_cw
        self.callback_ccw = callback_ccw
        self.callback_button = callback_button

class EncoderManager:
    def __init__(self, volume_pins, sound_select_pins):
        """Initialize manager for multiple rotary encoders.
        
        Args:
            volume_pins (tuple): Tuple of (clk, dt, sw) pins for volume encoder
            sound_select_pins (tuple): Tuple of (clk, dt, sw) pins for sound selection encoder"""
        GPIO.setmode(GPIO.BCM)
        
        # Volume encoder
        self.volume_encoder = RotaryEncoder(*volume_pins)
        
        # Sound selection encoder
        self.sound_select_encoder = RotaryEncoder(*sound_select_pins)
        
    def setup_volume_callbacks(self, volume_up, volume_down, volume_mute):
        """Configure callbacks for the volume control encoder.
        
        Args:
            volume_up (callable): Function to call when volume should increase
            volume_down (callable): Function to call when volume should decrease
            volume_mute (callable): Function to call when volume should be muted"""
        self.volume_encoder.set_callbacks(volume_up, volume_down, volume_mute)
        
    def setup_sound_select_callbacks(self, next_sound, prev_sound, play_selected):
        """Configure callbacks for the sound selection encoder.
        
        Args:
            next_sound (callable): Function to call to select next sound
            prev_sound (callable): Function to call to select previous sound
            play_selected (callable): Function to call to play selected sound"""
        self.sound_select_encoder.set_callbacks(next_sound, prev_sound, play_selected)
        
    def cleanup(self):
        """Clean up GPIO resources."""
        GPIO.cleanup()