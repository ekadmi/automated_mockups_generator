import os
import uuid
from typing import Dict, Tuple

from flask import Flask, request, send_from_directory, render_template_string
from werkzeug.utils import secure_filename

from calculate_box_pos import calculate_parameters
from create_mockups import create_mockups


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR = os.path.join(BASE_DIR, "runs")
os.makedirs(RUNS_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def allowed_file(filename: str) -> bool:
    if not filename:
        return False
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def parse_color(form) -> Tuple[int, int, int]:
    hex_color = (form.get("hex_color") or "").strip()
    if hex_color:
        hex_color = hex_color.lstrip("#")
        if len(hex_color) != 6:
            raise ValueError("Hex color must have 6 characters.")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return r, g, b

    r = int(form.get("r"))
    g = int(form.get("g"))
    b = int(form.get("b"))
    return r, g, b


def build_parameters(box_dir: str, target_color: Tuple[int, int, int]) -> Dict[str, Dict]:
    parameters: Dict[str, Dict] = {}
    for filename in os.listdir(box_dir):
        if not allowed_file(filename):
            continue
        image_path = os.path.join(box_dir, filename)
        bbox, height, width, rotation = calculate_parameters(image_path, target_color)
        if bbox and height and width:
            parameters[filename] = {
                "bbox": bbox,
                "height": height,
                "width": width,
                "rotation": rotation,
            }
    return parameters


app = Flask(__name__)


TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Automated Mockup Generator</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 960px; margin: 0 auto; padding: 24px; background: #f5f5f5; }
    h1 { margin-bottom: 8px; }
    h2 { margin-top: 24px; }
    .card { background: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); }
    .field { margin-bottom: 16px; }
    label { display: block; font-weight: 600; margin-bottom: 6px; }
    input[type="text"], input[type="number"] { width: 100%; padding: 8px; box-sizing: border-box; border-radius: 4px; border: 1px solid #ccc; }
    input[type="file"] { width: 100%; }
    .hint { font-size: 0.9em; color: #555; margin-top: 4px; }
    .error { background: #ffe6e6; color: #b00020; padding: 10px 12px; border-radius: 4px; margin-bottom: 16px; }
    .button { background: #1976d2; color: #ffffff; border: none; padding: 10px 18px; border-radius: 4px; font-size: 1rem; cursor: pointer; }
    .button:hover { background: #135ba1; }
    .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; margin-top: 16px; }
    .thumb { background: #ffffff; border-radius: 8px; padding: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); text-align: center; }
    .thumb img { max-width: 100%; border-radius: 4px; }
    .thumb-name { font-size: 0.85em; margin-top: 6px; word-break: break-all; }
    .back-link { display: inline-block; margin-top: 16px; text-decoration: none; color: #1976d2; }
  </style>
</head>
<body>
  <h1>Automated Mockup Generator</h1>
  <p>Upload your design files and matching mockups to generate product mockups in the browser.</p>
  <div class="card">
    {% if error %}
      <div class="error">{{ error }}</div>
    {% endif %}

    {% if outputs %}
      <h2>Generated mockups</h2>
      <div class="gallery">
        {% for image in outputs %}
          <div class="thumb">
            <img src="{{ url_for('serve_output', job_id=job_id, filename=image) }}" alt="{{ image }}">
            <div class="thumb-name">{{ image }}</div>
          </div>
        {% endfor %}
      </div>
      <a class="back-link" href="{{ url_for('index') }}">Generate more mockups</a>
    {% else %}
      <form method="post" enctype="multipart/form-data">
        <div class="field">
          <label for="designs">Design images</label>
          <input id="designs" type="file" name="designs" multiple required>
          <div class="hint">PNG or JPG files that you want to place on the mockups.</div>
        </div>

        <div class="field">
          <label for="mockups">Mockup images</label>
          <input id="mockups" type="file" name="mockups" multiple required>
          <div class="hint">Final mockup templates. Filenames must match the box mockups.</div>
        </div>

        <div class="field">
          <label for="box_mockups">Box mockup images</label>
          <input id="box_mockups" type="file" name="box_mockups" multiple required>
          <div class="hint">Reference mockups with a solid color box showing where the design goes.</div>
        </div>

        <div class="field">
          <label>Target color</label>
          <div class="hint">Use either HEX or RGB. If HEX is filled, it is used.</div>
          <div style="display: grid; grid-template-columns: 2fr 3fr; gap: 12px; align-items: center;">
            <div>
              <input type="text" name="hex_color" placeholder="#000000">
            </div>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;">
              <input type="number" name="r" min="0" max="255" placeholder="R">
              <input type="number" name="g" min="0" max="255" placeholder="G">
              <input type="number" name="b" min="0" max="255" placeholder="B">
            </div>
          </div>
        </div>

        <button class="button" type="submit">Generate mockups</button>
      </form>
    {% endif %}
  </div>
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template_string(TEMPLATE, error=None, outputs=None, job_id=None)

    try:
        target_color = parse_color(request.form)
    except Exception as exc:
        return render_template_string(TEMPLATE, error=str(exc), outputs=None, job_id=None), 400

    box_files = request.files.getlist("box_mockups")
    mockup_files = request.files.getlist("mockups")
    design_files = request.files.getlist("designs")

    if not box_files or not mockup_files or not design_files:
        return (
            render_template_string(
                TEMPLATE,
                error="Please upload at least one file for designs, mockups, and box mockups.",
                outputs=None,
                job_id=None,
            ),
            400,
        )

    job_id = uuid.uuid4().hex
    job_dir = os.path.join(RUNS_DIR, job_id)
    box_dir = os.path.join(job_dir, "box_mockups")
    mockup_dir = os.path.join(job_dir, "mockups")
    design_dir = os.path.join(job_dir, "designs")
    output_dir = os.path.join(job_dir, "output")

    os.makedirs(box_dir, exist_ok=True)
    os.makedirs(mockup_dir, exist_ok=True)
    os.makedirs(design_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    def save_files(files, target_dir):
        saved_any = False
        for f in files:
            if not f or not f.filename:
                continue
            filename = secure_filename(f.filename)
            if not allowed_file(filename):
                continue
            path = os.path.join(target_dir, filename)
            f.save(path)
            saved_any = True
        return saved_any

    saved_designs = save_files(design_files, design_dir)
    saved_mockups = save_files(mockup_files, mockup_dir)
    saved_boxes = save_files(box_files, box_dir)

    if not (saved_designs and saved_mockups and saved_boxes):
        return (
            render_template_string(
                TEMPLATE,
                error="No valid image files found. Use PNG or JPG files.",
                outputs=None,
                job_id=None,
            ),
            400,
        )

    parameters = build_parameters(box_dir, target_color)
    if not parameters:
        return (
            render_template_string(
                TEMPLATE,
                error="Could not detect any target boxes in the box mockups.",
                outputs=None,
                job_id=None,
            ),
            400,
        )

    create_mockups(design_dir, mockup_dir, parameters, output_dir)

    outputs = sorted(
        [name for name in os.listdir(output_dir) if allowed_file(name)],
        key=str.lower,
    )

    if not outputs:
        return (
            render_template_string(
                TEMPLATE,
                error="No output images were generated. Check that filenames match between mockups and box mockups.",
                outputs=None,
                job_id=None,
            ),
            400,
        )

    return render_template_string(
        TEMPLATE,
        error=None,
        outputs=outputs,
        job_id=job_id,
    )


@app.route("/runs/<job_id>/output/<path:filename>")
def serve_output(job_id: str, filename: str):
    directory = os.path.join(RUNS_DIR, job_id, "output")
    return send_from_directory(directory, filename)


if __name__ == "__main__":
    app.run(debug=True)

