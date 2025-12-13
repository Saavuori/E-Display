"""
Mock E-Paper Display Driver

Simulates the Waveshare e-paper display by saving high-quality preview images.
"""

import os
import numpy as np
from PIL import Image

class EPD:
    """Mock EPD class that simulates the e-paper display."""
    
    width = 800
    height = 480
    
    def __init__(self):
        self._preview_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        print(f"[MOCK EPD] Initialized mock display ({self.width}x{self.height})")
    
    def init(self):
        """Initialize the display (no-op for mock)."""
        print("[MOCK EPD] Display initialized")
    
    def Clear(self):
        """Clear the display (no-op for mock)."""
        print("[MOCK EPD] Display cleared")
    
    def sleep(self):
        """Put the display to sleep (no-op for mock)."""
        print("[MOCK EPD] Display sleeping")
    
    def getbuffer(self, image):
        """Convert image to buffer (just returns the image for mock)."""
        return image
    
    def display(self, image_bw, image_red):
        """Display the images by combining B/W and red layers into a high-quality preview."""
        print("[MOCK EPD] Displaying images...")
        
        # Create high-quality composite with antialiased e-paper look
        # Use 8-bit grayscale for smoother rendering
        composite = Image.new('RGB', (self.width, self.height), (252, 250, 245))  # Warm white like e-paper
        
        # Convert images to numpy for fast processing
        if isinstance(image_bw, Image.Image):
            bw_array = np.array(image_bw.convert('L'))
        else:
            bw_array = np.zeros((self.height, self.width), dtype=np.uint8)
            
        if isinstance(image_red, Image.Image):
            red_array = np.array(image_red.convert('L'))
        else:
            red_array = np.ones((self.height, self.width), dtype=np.uint8) * 255
        
        # Create composite array
        composite_array = np.array(composite)
        
        # Black pixels from B/W layer (where value < 128)
        black_mask = bw_array < 128
        composite_array[black_mask] = [25, 25, 30]  # Soft black like e-ink
        
        # Red pixels from red layer (where value < 128) - overlay on top
        red_mask = red_array < 128
        composite_array[red_mask] = [180, 40, 40]  # Muted red like e-paper
        
        # Convert back to image
        final = Image.fromarray(composite_array)
        
        # Save as high-quality PNG
        preview_path = os.path.join(self._preview_dir, 'preview.png')
        final.save(preview_path, 'PNG', optimize=False)
        print(f"[MOCK EPD] Preview saved to: {preview_path}")
