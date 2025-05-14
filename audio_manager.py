import os
import alsaaudio
import threading
import time
from pathlib import Path

class AudioManager:
    def __init__(self, audio_dir, mixer_device='Digital', mixer_control='PCM', oled_manager=None):
        """Initialize the audio manager with ALSA mixer and sound directory.
        
        Args:
            audio_dir (str): Directory containing WAV sound files
            mixer_device (str): ALSA mixer device name
            mixer_control (str): ALSA mixer control name
            oled_manager (OLEDManager, optional): OLED display manager for showing volume"""
        self.audio_dir = Path(audio_dir)
        self.oled_manager = oled_manager
        self.volume_display_thread = None
        self.previous_message = ""
        
        # Initialize ALSA mixer
        try:
            self.mixer = alsaaudio.Mixer(control=mixer_control, device=mixer_device)
            self.current_volume = self.mixer.getvolume()[0]
        except alsaaudio.ALSAAudioError:
            print(f"Warning: Could not open mixer {mixer_device}:{mixer_control}, falling back to default")
            self.mixer = alsaaudio.Mixer()
            self.current_volume = self.mixer.getvolume()[0]
        
        self.is_muted = False
        self._set_volume(self.current_volume)
        
    def play_sound(self, filename):
        """Play a WAV file using aplay.
        
        Args:
            filename (str): Name of the WAV file in the audio directory"""
        if self.is_muted:
            return
        
        file_path = self.audio_dir / filename
        if file_path.exists():
            # Use aplay for WAV playback
            os.system(f"aplay {str(file_path)}")
            
    def _display_volume_temporarily(self, message):
        """Show volume information on the OLED display for 5 seconds.
        
        Args:
            message (str): Volume message to display"""
        if not self.oled_manager:
            return
            
        def volume_display():
            # Store current message
            self.previous_message = self.oled_manager.message
            # Show volume
            self.oled_manager.set_message(message)
            # Wait 5 seconds
            time.sleep(5)
            # Restore previous message if it hasn't been changed
            if self.oled_manager.message == message:
                self.oled_manager.set_message(self.previous_message)
        
        # Cancel any existing volume display thread
        if self.volume_display_thread and self.volume_display_thread.is_alive():
            self.volume_display_thread.cancel()
        
        # Start new display thread
        self.volume_display_thread = threading.Timer(0, volume_display)
        self.volume_display_thread.start()
            
    def adjust_volume(self, delta):
        """Adjust the system volume by a relative amount.
        
        Args:
            delta (float): Volume adjustment between -1.0 and 1.0"""
        if self.is_muted:
            return
            
        # ALSA volume is 0-100
        new_volume = max(0, min(100, self.current_volume + int(delta * 100)))
        self._set_volume(new_volume)
        self._display_volume_temporarily(f"Volume: {self.current_volume}%")
        
    def toggle_mute(self):
        """Toggle the audio mute state and display the new state on the OLED."""
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.mixer.setmute(1)
            self._display_volume_temporarily("Volume: Muted")
        else:
            self.mixer.setmute(0)
            self._display_volume_temporarily(f"Volume: {self.current_volume}%")
        
    def _set_volume(self, volume):
        """Set the system volume to a specific level.
        
        Args:
            volume (int): Volume level between 0 and 100"""
        self.current_volume = volume
        self.mixer.setvolume(volume)
        
    def get_available_sounds(self):
        """Get a list of WAV files in the audio directory.
        
        Returns:
            list[str]: List of WAV filenames"""
        return [f.name for f in self.audio_dir.glob("*.wav")]
        
    def cleanup(self):
        """Clean up resources by canceling any active volume display thread."""
        if self.volume_display_thread and self.volume_display_thread.is_alive():
            self.volume_display_thread.cancel()