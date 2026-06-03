import os
import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

def main():
    # We need a QApplication instance to use QImage/QPainter/QSvgRenderer
    app = QApplication(sys.argv)
    
    script_dir = Path(__file__).resolve().parent
    svg_path = script_dir.parent / "app" / "resources" / "images" / "flowchart.svg"
    png_path = script_dir.parent / "app" / "resources" / "images" / "flowchart.png"
    
    if not svg_path.exists():
        print(f"Error: SVG file not found at {svg_path}")
        return 1
        
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        print("Error: Invalid SVG file")
        return 1
        
    # SVG viewBox is 0 0 900 480
    size = QSize(1800, 960) # High-res render (2x scale)
    image = QImage(size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    
    if image.save(str(png_path), "PNG"):
        print(f"Successfully rendered SVG to {png_path}")
        return 0
    else:
        print("Failed to save PNG image")
        return 1

if __name__ == "__main__":
    sys.exit(main())
