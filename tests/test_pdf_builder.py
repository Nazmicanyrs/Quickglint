"""Comprehensive Test Suite for Quickglint Professional PDF Document Builder & Editor."""

from pathlib import Path
import tempfile
import time

from PIL import Image
import pytest
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter

from app.pdf.commands import (
    AddObjectCommand,
    AddPageCommand,
    BatchCommand,
    CropImageCommand,
    DeleteObjectCommand,
    DeletePageCommand,
    DuplicatePageCommand,
    LayerOrderCommand,
    ReorderPageCommand,
    TextEditCommand,
    TransformObjectCommand,
)
from app.pdf.document import (
    BackgroundType,
    CropRect,
    DocumentSettings,
    ObjectType,
    PageBackground,
    PageNumberConfig,
    PDFAnnotationObject,
    PDFDocument,
    PDFImageObject,
    PDFLinkObject,
    PDFObject,
    PDFPage,
    PDFSecurityConfig,
    PDFShapeObject,
    PDFSignatureObject,
    PDFTextObject,
    ShapeType,
    SignatureType,
)
from app.pdf.history import PDFHistoryManager
from app.pdf.models import (
    FitMode,
    HeaderFooterConfig,
    MarginConfig,
    PageNumberPosition,
    PageOrientation,
    PaperSizePreset,
    QualityLevel,
)
from app.pdf.pdf_generator import (
    PDFGenerator,
    apply_pdf_security,
    validate_pdf_file,
)
from app.pdf.pdf_importer import PDFImporter
from app.pdf.render_engine import PDFRenderEngine


def create_test_qimage(w: int = 400, h: int = 300, color: QColor = QColor(50, 100, 150)) -> QImage:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(color)
    p = QPainter(img)
    p.setPen(QColor(255, 255, 255))
    p.drawText(20, 40, f"Test {w}x{h}")
    p.end()
    return img


# 1. Single screenshot -> PDFDocument
def test_single_screenshot_to_pdf_document():
    img = create_test_qimage(800, 600)
    doc = PDFDocument.create_from_image(img, title="Screenshot 1")

    assert len(doc.pages) == 1
    page = doc.pages[0]
    assert len(page.objects) == 1
    assert isinstance(page.objects[0], PDFImageObject)
    assert page.objects[0].title == "Screenshot 1"


# 2. Multi-page document (20 screenshots -> 20 pages)
def test_20_screenshots_to_20_page_pdf(tmp_path):
    images = [(create_test_qimage(200, 150), f"Shot {i+1}") for i in range(20)]
    doc = PDFDocument.create_from_images(images)

    assert len(doc.pages) == 20
    pdf_out = tmp_path / "twenty_pages.pdf"
    gen = PDFGenerator()
    success = gen.render_document_to_pdf(doc, pdf_out)

    assert success is True
    assert pdf_out.exists()
    assert validate_pdf_file(pdf_out) is True


# 3. Add 5 images to a single page
def test_add_5_images_to_single_page():
    page = PDFPage()
    for i in range(5):
        img_obj = PDFImageObject(
            image=create_test_qimage(100, 100),
            x_pt=i * 20.0,
            y_pt=i * 20.0,
            width_pt=80.0,
            height_pt=80.0,
            title=f"Image {i+1}",
        )
        page.add_object(img_obj)

    assert len(page.objects) == 5
    assert page.objects[-1].z_index == 4


# 4. Image Resize & Aspect ratio lock
def test_image_resize_and_aspect_lock():
    img = create_test_qimage(400, 200)  # 2:1 aspect ratio
    img_obj = PDFImageObject(image=img, width_pt=200.0, height_pt=100.0, lock_aspect_ratio=True)

    assert img_obj.lock_aspect_ratio is True
    assert img_obj.width == 200.0
    assert img_obj.height == 100.0


# 5. Non-destructive Image Crop
def test_image_non_destructive_crop():
    img = create_test_qimage(400, 400)
    img_obj = PDFImageObject(image=img, width_pt=200.0, height_pt=200.0)

    assert img_obj.crop.is_default() is True

    # Crop center quadrant [0.25, 0.25, 0.5, 0.5]
    img_obj.crop = CropRect(x=0.25, y=0.25, width=0.5, height=0.5)
    assert img_obj.crop.is_default() is False

    cropped = img_obj.get_cropped_image()
    assert cropped is not None
    assert cropped.width() == 200
    assert cropped.height() == 200

    # Original image is preserved intact!
    assert img_obj.original_image.width() == 400
    assert img_obj.original_image.height() == 400


# 6. Text Object and Typography
def test_text_object_properties():
    txt = PDFTextObject(
        text="Quickglint PDF Editor",
        font_family="Arial",
        font_size_pt=18.0,
        is_bold=True,
        is_italic=True,
        font_color="#2563EB",
        alignment="center",
    )

    assert txt.text == "Quickglint PDF Editor"
    assert txt.is_bold is True
    assert txt.is_italic is True
    assert txt.font_color == "#2563EB"
    assert txt.alignment == "center"


# 7. Rich Text HTML
def test_rich_text_html_object():
    html_content = "<b>Quickglint</b> <span style='color:red;'>PDF</span> <i>Editor</i>"
    txt = PDFTextObject(text="Quickglint PDF Editor", html=html_content)

    assert txt.html == html_content


# 8. Vector Shapes (Rectangle, Rounded Rect, Ellipse, Line, Arrow)
def test_vector_shapes():
    page = PDFPage()
    rect = PDFShapeObject(shape_type=ShapeType.RECTANGLE, fill_color="#3B82F6", border_color="#1D4ED8")
    rounded = PDFShapeObject(shape_type=ShapeType.ROUNDED_RECT, corner_radius_pt=8.0)
    circle = PDFShapeObject(shape_type=ShapeType.CIRCLE)
    arrow = PDFShapeObject(shape_type=ShapeType.ARROW)

    page.add_object(rect)
    page.add_object(rounded)
    page.add_object(circle)
    page.add_object(arrow)

    assert len(page.objects) == 4
    assert page.objects[1].corner_radius_pt == 8.0


# 9. Freehand Annotations
def test_freehand_annotations():
    page = PDFPage()
    pen_ann = PDFAnnotationObject(tool="pen", color="#EF4444", points=[(10, 10), (20, 20), (30, 15)])
    hl_ann = PDFAnnotationObject(tool="highlighter", color="#FACC15", points=[(50, 50), (100, 50)])

    page.add_object(pen_ann)
    page.add_object(hl_ann)

    assert len(page.objects) == 2
    assert len(page.objects[0].points) == 3


# 10. Hyperlinks (External URL & Internal Page Jump)
def test_hyperlinks_and_page_jumps():
    link_obj = PDFLinkObject(url="https://Quickglint.example.com", target_page=2)
    assert link_obj.hyperlink_url == "https://Quickglint.example.com"
    assert link_obj.internal_link_page == 2


# 11. Signature Object (Drawn & Typed)
def test_signature_object():
    drawn_sig = PDFSignatureObject(
        sig_type=SignatureType.DRAWN,
        points=[[(0.1, 0.5), (0.3, 0.2), (0.5, 0.8)]],
        ink_color="#0F172A",
    )
    typed_sig = PDFSignatureObject(
        sig_type=SignatureType.TYPED,
        typed_text="Jane Doe",
        typed_font="Segoe Script",
    )

    assert drawn_sig.sig_type == SignatureType.DRAWN
    assert typed_sig.typed_text == "Jane Doe"


# 12. Page Management: Add, Duplicate, Reorder, Delete
def test_page_management():
    doc = PDFDocument.create_empty("Test Doc")
    assert len(doc.pages) == 1

    p2 = doc.add_page(PDFPage())
    assert len(doc.pages) == 2

    # Duplicate page 0
    p_dup = doc.duplicate_page(0)
    assert p_dup is not None
    assert len(doc.pages) == 3

    # Move page 0 to index 2
    doc.move_page(0, 2)
    assert len(doc.pages) == 3

    # Delete
    doc.remove_page(0)
    assert len(doc.pages) == 2


# 13. Layer Ordering (Bring to Front, Send to Back)
def test_layer_ordering():
    page = PDFPage()
    obj1 = PDFShapeObject(shape_type=ShapeType.RECTANGLE)
    obj2 = PDFTextObject(text="Front")
    obj3 = PDFImageObject(image=create_test_qimage(50, 50))

    page.add_object(obj1)
    page.add_object(obj2)
    page.add_object(obj3)

    assert obj1.z_index == 0
    assert obj2.z_index == 1
    assert obj3.z_index == 2

    # Send obj3 to back
    page.send_to_back(obj3)
    assert page.objects[0] == obj3

    # Bring obj1 to front
    page.bring_to_front(obj1)
    assert page.objects[-1] == obj1


# 14. Command Pattern Undo / Redo
def test_history_undo_redo():
    history = PDFHistoryManager()
    page = PDFPage()
    txt = PDFTextObject(text="Initial")

    # Add object command
    cmd_add = AddObjectCommand(page, txt)
    history.push(cmd_add)
    assert len(page.objects) == 1
    assert history.can_undo is True

    # Undo
    assert history.undo() is True
    assert len(page.objects) == 0
    assert history.can_redo is True

    # Redo
    assert history.redo() is True
    assert len(page.objects) == 1

    # Text edit command
    cmd_edit = TextEditCommand(page, txt, old_text="Initial", new_text="Edited", old_html="", new_html="")
    history.push(cmd_edit)
    assert txt.text == "Edited"

    history.undo()
    assert txt.text == "Initial"

    history.redo()
    assert txt.text == "Edited"


# 15. Transform & Crop Undo / Redo
def test_transform_and_crop_undo():
    history = PDFHistoryManager()
    page = PDFPage()
    img_obj = PDFImageObject(image=create_test_qimage(100, 100), x_pt=0, y_pt=0, width_pt=100, height_pt=100)
    page.add_object(img_obj)

    # Transform
    cmd_trans = TransformObjectCommand(
        page=page,
        obj=img_obj,
        old_rect=QRectF(0, 0, 100, 100),
        new_rect=QRectF(50, 50, 200, 200),
        old_rotation=0.0,
        new_rotation=45.0,
    )
    history.push(cmd_trans)
    assert img_obj.x == 50
    assert img_obj.rotation == 45.0

    history.undo()
    assert img_obj.x == 0
    assert img_obj.rotation == 0.0

    # Crop Command
    cmd_crop = CropImageCommand(
        page=page,
        image_obj=img_obj,
        old_crop=CropRect(),
        new_crop=CropRect(0.1, 0.1, 0.8, 0.8),
    )
    history.push(cmd_crop)
    assert img_obj.crop.x == 0.1

    history.undo()
    assert img_obj.crop.x == 0.0


# 16. Project Serialization & Recovery (.quickglintpdf)
def test_save_and_reopen_quickglintpdf_project(tmp_path):
    doc = PDFDocument.create_empty("My Great Project")
    page = doc.pages[0]
    page.add_object(PDFTextObject(text="Project Text", is_bold=True))
    page.add_object(PDFShapeObject(shape_type=ShapeType.ROUNDED_RECT, fill_color="#22C55E"))
    page.add_object(PDFImageObject(image=create_test_qimage(120, 80), title="Test Embedded"))

    proj_file = tmp_path / "project.quickglintpdf"
    assert doc.save_project(proj_file) is True
    assert proj_file.exists()

    # Reopen
    loaded = PDFDocument.load_project(proj_file)
    assert loaded is not None
    assert loaded.settings.title == "My Great Project"
    assert len(loaded.pages) == 1
    loaded_page = loaded.pages[0]
    assert len(loaded_page.objects) == 3

    assert isinstance(loaded_page.objects[0], PDFTextObject)
    assert loaded_page.objects[0].text == "Project Text"
    assert loaded_page.objects[0].is_bold is True

    assert isinstance(loaded_page.objects[1], PDFShapeObject)
    assert loaded_page.objects[1].fill_color == "#22C55E"

    assert isinstance(loaded_page.objects[2], PDFImageObject)
    assert loaded_page.objects[2].original_image is not None
    assert loaded_page.objects[2].original_image.width() == 120


# 17. Searchable OCR Layer
def test_ocr_searchable_text_layer():
    txt_ocr = PDFTextObject(text="Recognized Text via OCR", is_ocr_layer=True)
    assert txt_ocr.is_ocr_layer is True
    assert txt_ocr.text == "Recognized Text via OCR"


# 18. PDF Security Encryption
def test_pdf_security_config(tmp_path):
    doc = PDFDocument.create_from_image(create_test_qimage(300, 200), title="Confidential")
    doc.settings.security = PDFSecurityConfig(
        enabled=True,
        user_password="secret123",
        allow_printing=False,
    )

    pdf_out = tmp_path / "encrypted.pdf"
    gen = PDFGenerator()
    success = gen.render_document_to_pdf(doc, pdf_out)
    assert success is True
    assert pdf_out.exists()
    assert validate_pdf_file(pdf_out) is True


# 19. Complete End-to-End Multi-Element PDF Generation
def test_end_to_end_complex_pdf_generation(tmp_path):
    doc = PDFDocument.create_empty("Full Showcase Document")
    page1 = doc.pages[0]
    page1.paper_size = PaperSizePreset.A4
    page1.orientation = PageOrientation.PORTRAIT

    # Add Image
    page1.add_object(PDFImageObject(image=create_test_qimage(600, 400), x_pt=50, y_pt=60, width_pt=400, height_pt=266))

    # Add Shapes
    page1.add_object(PDFShapeObject(shape_type=ShapeType.ROUNDED_RECT, x_pt=50, y_pt=350, width_pt=200, height_pt=80, fill_color="#06B6D4"))

    # Add Text
    page1.add_object(PDFTextObject(text="Executive Overview", x_pt=60, y_pt=365, font_size_pt=18.0, is_bold=True, font_color="#FFFFFF"))

    # Add Signature
    page1.add_object(PDFSignatureObject(sig_type=SignatureType.TYPED, typed_text="Authorized Signature", x_pt=300, y_pt=450))

    # Add Page 2
    page2 = doc.add_page(PDFPage(paper_size=PaperSizePreset.A4, orientation=PageOrientation.LANDSCAPE))
    page2.add_object(PDFTextObject(text="Landscape Appendix Page", x_pt=100, y_pt=100, font_size_pt=24.0))

    # Configure Header/Footer & Page Numbering
    doc.settings.header_footer = HeaderFooterConfig(
        header_text="Quickglint PDF Showcase — {title}",
        footer_text="Generated on {date}",
    )
    doc.settings.page_numbers = PageNumberConfig(
        enabled=True,
        position=PageNumberPosition.BOTTOM_RIGHT,
        format_template="Page {page} of {pages}",
    )

    pdf_out = tmp_path / "showcase.pdf"
    gen = PDFGenerator()
    success = gen.render_document_to_pdf(doc, pdf_out)

    assert success is True
    assert pdf_out.exists()
    assert validate_pdf_file(pdf_out) is True

