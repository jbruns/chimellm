import os
import json
import time
import yaml
import logging
from pathlib import Path
from datetime import datetime
import paho.mqtt.client as mqtt

from audio_manager import AudioManager
from hdmi_manager import HDMIManager
from oled_manager import OLEDManager
from encoder_manager import EncoderManager
from shairport_manager import ShairportManager

class DoorbellSystem:
    def __init__(self):
        """Initialize the doorbell system with all required components.
        Sets up logging, loads config, and initializes OLED, audio, HDMI, Shairport,
        encoder managers and MQTT client."""
        # Setup logging
        logging.basicConfig(
            format='%(asctime)s - %(levelname)s - %(message)s',
            level=logging.INFO
        )
        self.logger = logging.getLogger(__name__)
        
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
        """Toggle the HDMI display on/off.
        When turning on, automatically starts playing the default video stream."""
        if self.hdmi.is_display_on:
            self.hdmi.turn_off_display()
        else:
            self.hdmi.turn_on_display()
            self.hdmi.play_video(self.config['video']['default_stream'])
            
    def setup_encoder_callbacks(self):
        """Configure the rotary encoder callbacks for volume control and sound selection.
        Volume encoder: Controls system volume and mute
        Sound selection encoder: Controls sound selection and display toggle"""
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
        """Select the next available doorbell sound in the list.
        Updates the OLED display to show the newly selected sound."""
        if self.available_sounds:
            self.selected_sound_index = (self.selected_sound_index + 1) % len(self.available_sounds)
            self.oled.show_sound_selection(self.available_sounds[self.selected_sound_index])
            
    def prev_sound(self):
        """Select the previous available doorbell sound in the list.
        Updates the OLED display to show the newly selected sound."""
        if self.available_sounds:
            self.selected_sound_index = (self.selected_sound_index - 1) % len(self.available_sounds)
            self.oled.show_sound_selection(self.available_sounds[self.selected_sound_index])
            
    def play_selected_sound(self):
        """Play the currently selected doorbell sound.
        Also turns on the HDMI display and starts the default video stream."""
        if self.available_sounds:
            # Update the active sound index when explicitly selected
            self.current_sound_index = self.selected_sound_index
            self.hdmi.turn_on_display()
            self.audio.play_sound(self.available_sounds[self.current_sound_index])
            self.hdmi.play_video(self.config['video']['default_stream'])
            
    def on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback. Subscribes to doorbell, motion, and message topics.
        
        Args:
            client: MQTT client instance
            userdata: Private user data
            flags: Connection flags
            rc: Connection result code"""
        topics = [
            (self.config['mqtt']['topics']['doorbell'], 0),
            (self.config['mqtt']['topics']['motion'], 0),
            (self.config['mqtt']['topics']['message'], 0)
        ]
        client.subscribe(topics)
        
    def handle_event_message(self, topic, payload):
        """Process doorbell and motion detection events from MQTT messages.
        
        Args:
            topic (str): MQTT topic of the message
            payload (dict): Message payload containing 'active', 'timestamp', and 'video_url'
        
        Raises:
            ValueError: If payload is invalid or missing required fields"""
        try:
            if not isinstance(payload, dict):
                raise ValueError("Payload must be a JSON object")
                
            # Check for required fields
            if not all(key in payload for key in ['active', 'timestamp', 'video_url']):
                raise ValueError("Missing required fields in payload")
                
            # Convert timestamp string to datetime
            try:
                event_time = datetime.fromisoformat(payload['timestamp'])
            except (ValueError, TypeError):
                raise ValueError("Invalid timestamp format")
                
            # Handle based on event type
            if topic == self.config['mqtt']['topics']['motion']:
                # Update motion time with active state
                self.oled.update_motion_time(event_time, payload['active'])
                # Handle message display
                if payload['active']:
                    self.oled.set_event_message("Motion detected on doorbell camera!")
                else:
                    self.oled.restore_previous_message()
            else:  # Doorbell event
                if payload['active']:
                    self.oled.set_event_message("Someone's at the door!")
                else:
                    self.oled.restore_previous_message()
            
            # Handle active state display and actions
            if payload['active']:
                self.hdmi.turn_on_display()
                # For doorbell events, also play the sound
                if topic == self.config['mqtt']['topics']['doorbell']:
                    self.audio.play_sound(self.config['audio']['default_sound'])
                # Use provided video URL or fall back to default
                video_url = payload['video_url'] or self.config['video']['default_stream']
                self.hdmi.play_video(video_url)
                
        except (ValueError, TypeError) as e:
            self.logger.error(f"Error processing {topic} message: {str(e)}")
            self.logger.debug(f"Problematic payload: {payload}")
            
    def on_message(self, client, userdata, msg):
        """MQTT message callback. Routes messages to appropriate handlers based on topic.
        
        Args:
            client: MQTT client instance
            userdata: Private user data
            msg: Received message containing topic and payload"""
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode())
            
            if topic in [self.config['mqtt']['topics']['doorbell'], 
                        self.config['mqtt']['topics']['motion']]:
                self.handle_event_message(topic, payload)
            elif topic == self.config['mqtt']['topics']['message']:
                self.handle_message(payload)
                
        except json.JSONDecodeError:
            self.logger.error(f"Invalid JSON received on topic {topic}")
            self.logger.debug(f"Raw payload: {msg.payload}")
            
    def handle_message(self, payload):
        """Process generic message events and display them on the OLED screen.
        
        Args:
            payload (Union[dict, str]): Message payload, either a dict with 'text' key or a string"""
        if isinstance(payload, dict) and 'text' in payload:
            self.oled.set_message(payload['text'])
        else:
            self.oled.set_message(str(payload))
            
    def run(self):
        """Main system loop. Connects to MQTT broker, starts Shairport monitoring,
        and continuously updates the OLED display."""
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
        """Clean up system resources on shutdown.
        Stops MQTT client, encoders, HDMI, audio, Shairport, and OLED managers."""
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