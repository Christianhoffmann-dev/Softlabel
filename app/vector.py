"""SVG-Rasterisierung mit exakter DPI — genutzt für Barcodes und Assets.

PyMuPDF rendert das mm-basierte Barcode-SVG direkt in die Ziel-Auflösung des
Druckers (Standard 300 dpi), damit Strichbreiten druckgenau erhalten bleiben.
"""
import io


def rasterize_svg(svg_bytes: bytes, dpi: int) -> tuple[bytes, int, int]:
    """Wandelt SVG (Einheiten mm) in PNG bei dpi um. Gibt (png, w_px, h_px) zurück."""
    import fitz  # PyMuPDF
    doc = fitz.open(stream=svg_bytes, filetype="svg")
    page = doc[0]
    zoom = dpi / 72.0  # SVG-Punkte = mm-Werte, 72 pt = 1 inch
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    out = pix.tobytes("png")
    w, h = pix.width, pix.height
    doc.close()
    return out, w, h


def png_size(png_bytes: bytes) -> tuple[int, int]:
    from PIL import Image
    with Image.open(io.BytesIO(png_bytes)) as img:
        return img.size
