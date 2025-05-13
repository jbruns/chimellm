import os
import json
import time
import yaml
from pathlib import Path
import paho.mqtt.client as mqtt

from audio_manager import AudioManager
from hdmi_manager import HDMIManager
from oled_manager import OLEDManager
from encoder_manager import EncoderManager
from shairport_manager import ShairportManager

class DoorbellSystem:
    def __init__(self):
        with open('config.yaml', 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Initialize OLED first since other components need it
        self.oled = OLEDManager(
            self.config['displays']['oled']['i2c_port'],
            self.config['displays']['oled']['i2c_address']
        )
        
        # Initialize managers
        self.audio = AudioManager(
            self.config['audio']['directory'],
            mixer_device=self.config['audio']['mixer']['device'],
            mixer_control=self.config['audio']['mixer']['control'],
            oled_manager=self.oled
        )
        
        self.hdmi = HDMIManager(self.config['displays']['hdmi']['framebuffer'])
        
        # Initialize Shairport metadata handling
        self.shairport = ShairportManager(
            self.config['shairport']['metadata_pipe'],
            oled_manager=self.oled,
            show_duration=self.config['shairport']['show_duration']
        )
        
        # Setup encoders
        self.encoders = EncoderManager(
            volume_pins=(
                self.config['gpio']['volume_encoder']['clk'],
                self.config['gpio']['volume_encoder']['dt'],
                self.config['gpio']['volume_encoder']['sw']
            ),
            sound_select_pins=(
                self.config['gpio']['sound_select_encoder']['clk'],
                self.config['gpio']['sound_select_encoder']['dt'],
                self.config['gpio']['sound_select_encoder']['sw']
            )
        )
        
        # Setup MQTT client
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        
        # State management
        self.current_sound_index = 0
        self.selected_sound_index = 0  # Track currently selected vs active sound
        self.available_sounds = self.audio.get_available_sounds()
        
        # Setup encoder callbacks
        self.setup_encoder_callbacks()
        
    def toggle_display(self):
        """New method to handle display toggle"""
        if self.hdmi.is_display_on:
            self.hdmi.turn_off_display()
        else:
            self.hdmi.turn_on_display()
            self.hdmi.play_video(self.config['video']['default_stream'])
            
    def setup_encoder_callbacks(self):
        # Volume encoder
        self.encoders.setup_volume_callbacks(
            volume_up=lambda: self.audio.adjust_volume(0.05),
            volume_down=lambda: self.audio.adjust_volume(-0.05),
            volume_mute=self.audio.toggle_mute
        )
        
        # Sound selection encoder - update button callback to toggle display
        self.encoders.setup_sound_select_callbacks(
            next_sound=self.next_sound,
            prev_sound=self.prev_sound,
            play_selected=self.toggle_display
        )
        
    def next_sound(self):
        if self.available_sounds:
            self.selected_sound_index = (self.selected_sound_index + 1) % len(self.available_sounds)
            self.oled.show_sound_selection(self.available_sounds[self.selected_sound_index])
            
    def prev_sound(self):
        if self.available_sounds:
            self.selected_sound_index = (self.selected_sound_index - 1) % len(self.available_sounds)
            self.oled.show_sound_selection(self.available_sounds[self.selected_sound_index])
            
    def play_selected_sound(self):
        if self.available_sounds:
            # Update the active sound index when explicitly selected
            self.current_sound_index = self.selected_sound_index
            self.hdmi.turn_on_display()
            self.audio.play_sound(self.available_sounds[self.current_sound_index])
            self.hdmi.play_video(self.config['video']['default_stream'])
            
    def on_connect(self, client, userdata, flags, rc):
        topics = [
            (self.config['mqtt']['topics']['doorbell'], 0),
            (self.config['mqtt']['topics']['motion'], 0),
            (self.config['mqtt']['topics']['message'], 0)
        ]
        client.subscribe(topics)
        
    def on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            payload = msg.payload.decode()
            
        if topic == self.config['mqtt']['topics']['doorbell']:
            self.handle_doorbell(payload)
        elif topic == self.config['mqtt']['topics']['motion']:
            self.handle_motion(payload)
        elif topic == self.config['mqtt']['topics']['message']:
            self.handle_message(payload)
            
    def handle_doorbell(self, payload):
        self.hdmi.turn_on_display()
        self.audio.play_sound(self.config['audio']['default_sound'])
        if isinstance(payload, dict) and 'video_url' in payload:
            self.hdmi.play_video(payload['video_url'])
        else:
            self.hdmi.play_video(self.config['video']['default_stream'])
            
    def handle_motion(self, payload):
        self.oled.update_motion_time()
        self.hdmi.turn_on_display()
        if isinstance(payload, dict) and 'video_url' in payload:
            self.hdmi.play_video(payload['video_url'])
        else:
            self.hdmi.play_video(self.config['video']['default_stream'])
            
    def handle_message(self, payload):
        if isinstance(payload, dict) and 'text' in payload:
            self.oled.set_message(payload['text'])
        else:
            self.oled.set_message(str(payload))
            
    def run(self):
        # Connect to MQTT broker
        mqtt_username = self.config['mqtt']['username']
        mqtt_password = self.config['mqtt']['password']
        if mqtt_username and mqtt_password:
            self.mqtt_client.username_pw_set(mqtt_username, mqtt_password)
            
        self.mqtt_client.connect(
            self.config['mqtt']['broker'],
            self.config['mqtt']['port'],
            60
        )
        self.mqtt_client.loop_start()
        
        # Start Shairport metadata monitoring
        self.shairport.start()
        
        try:
            while True:
                self.oled.update_display()
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.cleanup()
            
    def cleanup(self):
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        self.encoders.cleanup()
        self.hdmi.turn_off_display()
        self.audio.cleanup()
        self.shairport.stop()  # Stop Shairport metadata monitoring
        self.oled.cleanup()

if __name__ == "__main__":
    system = DoorbellSystem()
    system.run()