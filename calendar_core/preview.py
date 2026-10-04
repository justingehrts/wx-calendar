import io
import pypdfium2 as pdfium

def pdf_to_pngs(pdf_bytes, scale=1.6, grayscale=False):
    """Rasterize every page. grayscale=True shows what a B&W printer will produce from a color PDF."""
    pdf = pdfium.PdfDocument(pdf_bytes); out = []
    for i in range(len(pdf)):
        img = pdf[i].render(scale=scale).to_pil().convert("RGB")
        if grayscale: img = img.convert("L")
        b = io.BytesIO(); img.save(b, "PNG"); out.append(b.getvalue())
    return out
