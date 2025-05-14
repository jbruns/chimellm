import time
from datetime import datetime
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1305
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import threading

class OLEDManager:
    def __init__(self, i2c_port, i2c_address):
        serial = i2c(port=i2c_port, address=i2c_address)
        self.device = ssd1305(serial, width=128, height=32)
        self.device.contrast(255)
        self.last_motion_time = None
        self.motion_active = False
        self.message = ""
        self.scroll_position = 0
        self.scroll_start_time = None
        self.scroll_paused = True
        self.temporary_display = False
        self.temp_display_thread = None
        self.prev_message = ""
        self.temp_message = None
        self.temp_message_thread = None
        self.pre_event_message = None
        
        # Load fonts - try to find an emoji-capable font, fallback to regular font
        try:
            self.font = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 8)
        except OSError:
            try:
                self.font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 8)
            except OSError:
                self.font = ImageFont.load_default()
        
    def update_motion_time(self, timestamp=None, active=False):
        """Update the last motion time and active state"""
        self.last_motion_time = timestamp or datetime.now()
        self.motion_active = active
        
    def set_message(self, message):
        self.message = message
        self.scroll_position = 0
        self.scroll_start_time = None
        self.scroll_paused = True
        
    def set_event_message(self, message):
        """Set a temporary message for an active event, storing the previous message"""
        if self.pre_event_message is None:
            self.pre_event_message = self.message
        self.message = message
        
    def show_temporary_message(self, message, duration):
        """Show a temporary message and revert to previous state after duration"""
        def restore_message():
            if self.temp_message == message:  # Only restore if no new temp message
                self.temp_message = None
                self.message = self.prev_message
                
        # Store current message if this is a new temporary message
        if not self.temp_message:
            self.prev_message = self.message
            
        # Update temporary message
        self.temp_message = message
        self.message = message
        
        # Reset scroll state
        self.scroll_position = 0
        self.scroll_start_time = None
        self.scroll_paused = True
        
        # Cancel existing timer if any
        if self.temp_message_thread and self.temp_message_thread.is_alive():
            self.temp_message_thread.cancel()
            
        # Start new timer
        self.temp_message_thread = threading.Timer(duration, restore_message)
        self.temp_message_thread.start()
        
    def restore_previous_message(self):
        """Restore the message from before an event"""
        if self.pre_event_message is not None:
            self.message = self.pre_event_message
            self.pre_event_message = None
        elif self.temp_message:
            self.temp_message = None
            self.message = self.prev_message
        
    def _get_motion_time_text(self):
        if self.motion_active:
            return "now"
        if self.last_motion_time is None:
            return "??"
        delta = datetime.now() - self.last_motion_time
        minutes = int(delta.total_seconds() / 60)
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        return f"{hours}h {minutes%60}m"
        
    def _draw_separator_line(self, draw, y_pos):
        """Draw a single pixel horizontal line"""
        draw.line([(0, y_pos), (self.device.width-1, y_pos)], fill="white", width=1)
        
    def _draw_vertical_separator(self, draw, x_pos, y_start, y_end):
        """Draw a single pixel vertical line"""
        draw.line([(x_pos, y_start), (x_pos, y_end)], fill="white", width=1)
        
    def _truncate_filename(self, filename, max_width, draw):
        """Truncate filename if it's too wide for display"""
        if draw.textlength(filename, font=self.font) <= max_width:
            return filename
        
        while draw.textlength(filename[:-3] + "...", font=self.font) > max_width and len(filename) > 3:
            filename = filename[:-4] + "..."
        return filename
        
    def _center_text(self, text, draw, area_width, area_height, y_offset=0):
        """Calculate position to center text in given area"""
        text_width = draw.textlength(text, font=self.font)
        text_height = self.font.getsize(text)[1]  # Get text height
        x = (area_width - text_width) // 2
        y = y_offset + (area_height - text_height) // 2
        return x, y
        
    def show_sound_selection(self, filename):
        """Show sound selection screen temporarily"""
        def restore_display():
            if self.temporary_display:
                self.temporary_display = False
                self.message = self.prev_message
                
        # Cancel any existing temporary display
        if self.temp_display_thread and self.temp_display_thread.is_alive():
            self.temp_display_thread.cancel()
            
        # Store current state
        if not self.temporary_display:
            self.prev_message = self.message
            
        self.temporary_display = True
        self.temp_filename = filename
        
        # Set timer to restore display after 5 seconds of no updates
        self.temp_display_thread = threading.Timer(5.0, restore_display)
        self.temp_display_thread.start()
        
    def update_display(self):
        with canvas(self.device) as draw:
            if self.temporary_display:
                # Display sound selection screen
                title = "Doorbell sound:"
                
                # Calculate center positions for two lines of text
                title_x, title_y = self._center_text(title, draw, self.device.width, 16, 0)
                
                # Truncate filename if needed and center it
                truncated_filename = self._truncate_filename(self.temp_filename, self.device.width, draw)
                filename_x, filename_y = self._center_text(truncated_filename, draw, self.device.width, 16, 16)
                
                # Draw centered text
                draw.text((title_x, title_y), title, font=self.font, fill="white")
                draw.text((filename_x, filename_y), truncated_filename, font=self.font, fill="white")
                
            else:
                # Top quarter: time and motion info
                current_time = datetime.now().strftime("%m/%d %H:%M")
                
                # Left-justified time with clock emoji
                time_text = "🕐 " + current_time
                draw.text((0, 0), time_text, font=self.font, fill="white")
                
                # Right-justified motion info with walking emoji and vertical separator
                motion_text = "🚶 " + self._get_motion_time_text()
                motion_width = draw.textlength(motion_text, font=self.font)
                
                # Calculate vertical separator position (75% of display width)
                separator_x = int(self.device.width * 0.75)
                self._draw_vertical_separator(draw, separator_x, 0, 8)
                
                # Draw motion text right-justified after separator
                draw.text((self.device.width - motion_width, 0), motion_text, font=self.font, fill="white")
                
                # Draw horizontal separator line
                self._draw_separator_line(draw, 9)
                
                # Bottom 3/4: scrolling message
                if self.message:
                    # Calculate text width to determine if scrolling is needed
                    msg_width = draw.textlength(self.message, font=self.font)
                    
                    if msg_width > self.device.width:
                        current_time = time.time()
                        
                        # Initialize scroll_start_time if not set
                        if self.scroll_start_time is None:
                            self.scroll_start_time = current_time
                            
                        # Check if we're in initial delay period (2 seconds)
                        if current_time - self.scroll_start_time < 2.0:
                            x_pos = self.device.width
                        # Check if we've reached the end and need to pause
                        elif self.scroll_paused and current_time - self.scroll_start_time >= 2.0:
                            self.scroll_paused = False
                            self.scroll_position = 0
                        # Check if we need to pause at the end
                        elif self.scroll_position >= msg_width and not self.scroll_paused:
                            self.scroll_paused = True
                            self.scroll_start_time = current_time
                        # Normal scrolling
                        elif not self.scroll_paused:
                            self.scroll_position += 1
                            
                        # Draw the text at current position
                        x_pos = self.device.width - self.scroll_position
                        draw.text((x_pos, 16), self.message, font=self.font, fill="white")
                    else:
                        # Center text if it fits
                        x_pos = (self.device.width - msg_width) // 2
                        draw.text((x_pos, 16), self.message, font=self.font, fill="white")
                        
    def cleanup(self):
        """Cleanup any running threads"""
        if self.temp_message_thread and self.temp_message_thread.is_alive():
            self.temp_message_thread.cancel()
        if self.temp_display_thread and self.temp_display_thread.is_alive():
            self.temp_display_thread.cancel()