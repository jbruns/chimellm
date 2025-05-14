import threading
import time
from shairport_sync_metadata.metadata_reader import MetadataReader
from shairport_sync_metadata.metadata import Item

class ShairportManager:
    def __init__(self, pipe_path, oled_manager=None, show_duration=10):
        """Initialize Shairport Sync metadata manager.
        
        Args:
            pipe_path (str): Path to the Shairport Sync metadata pipe
            oled_manager (OLEDManager, optional): OLED display for showing track info
            show_duration (int): How long to show track info in seconds"""
        self.pipe_path = pipe_path
        self.oled_manager = oled_manager
        self.show_duration = show_duration
        self.reader = None
        self.reader_thread = None
        self.running = False
        self.current_track = None
        self.display_thread = None
        
    def start(self):
        """Start monitoring Shairport Sync metadata in a background thread."""
        self.running = True
        self.reader_thread = threading.Thread(target=self._read_metadata)
        self.reader_thread.daemon = True
        self.reader_thread.start()
        
    def stop(self):
        """Stop monitoring metadata and clean up resources."""
        self.running = False
        if self.reader:
            self.reader.stop()
        if self.reader_thread:
            self.reader_thread.join()
        if self.display_thread and self.display_thread.is_alive():
            self.display_thread.cancel()
            
    def _handle_metadata(self, item: Item):
        """Process metadata items from Shairport.
        
        Args:
            item (Item): Metadata item containing type, code, and text"""
        if not item or not item.type:
            return
            
        if item.type == 'ssnc' and item.code == 'pend':
            # Playback ended
            self.current_track = None
            if self.display_thread and self.display_thread.is_alive():
                self.display_thread.cancel()
        elif item.type == 'core':
            if item.code == 'asal':  # Album name
                self.current_track = self.current_track or {}
                self.current_track['album'] = item.text
            elif item.code == 'asar':  # Artist name
                self.current_track = self.current_track or {}
                self.current_track['artist'] = item.text
            elif item.code == 'minm':  # Track title
                self.current_track = self.current_track or {}
                self.current_track['title'] = item.text
                self._update_display()
                
    def _update_display(self):
        """Update the OLED display with current track information.
        Shows artist and title for show_duration seconds."""
        if not self.oled_manager or not self.current_track:
            return
            
        def restore_display():
            # Only restore if we're not showing a different track
            if self.oled_manager.message.startswith("♫"):
                self.oled_manager.restore_previous_message()
                
        # Format track info
        track_info = "♫ "
        if 'title' in self.current_track:
            track_info += self.current_track['title']
        if 'artist' in self.current_track:
            track_info += f" - {self.current_track['artist']}"
            
        # Cancel any existing display timer
        if self.display_thread and self.display_thread.is_alive():
            self.display_thread.cancel()
            
        # Show track info
        self.oled_manager.show_temporary_message(track_info, self.show_duration)
        
    def _read_metadata(self):
        """Background thread function that reads metadata from Shairport pipe.
        Continuously reads and processes metadata while running is True."""
        while self.running:
            try:
                self.reader = MetadataReader(self.pipe_path)
                for item in self.reader.items():
                    if not self.running:
                        break
                    self._handle_metadata(item)
            except Exception as e:
                print(f"Error reading Shairport metadata: {e}")
                time.sleep(5)  # Wait before retrying