import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "training"))

from prepare_dataset import voc_to_yolo  # noqa: E402

VOC = """<annotation>
  <filename>potholes0.png</filename>
  <size><width>400</width><height>200</height><depth>3</depth></size>
  <object><name>pothole</name><bndbox><xmin>100</xmin><ymin>50</ymin><xmax>200</xmax><ymax>150</ymax></bndbox></object>
  <object><name>pothole</name><bndbox><xmin>350</xmin><ymin>150</ymin><xmax>450</xmax><ymax>250</ymax></bndbox></object>
</annotation>"""


def test_voc_to_yolo(tmp_path):
    xml = tmp_path / "potholes0.xml"
    xml.write_text(VOC)
    filename, lines = voc_to_yolo(str(xml))
    assert filename == "potholes0.png"
    assert lines[0] == "0 0.375000 0.500000 0.250000 0.500000"
    # Second box spills past the image edge and is clamped to (350,150)-(400,200)
    assert lines[1] == "0 0.937500 0.875000 0.125000 0.250000"
