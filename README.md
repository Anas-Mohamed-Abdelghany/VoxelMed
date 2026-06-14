# MedView3D: Multi-Planar Medical Image Viewer & AI Exploration Platform

Developed as part of the **"AI for Real-World Response" Hackathon (Track 1 - Medical Sector)** by Anas, Zyad, Hassan, and Nada.

`MedView3D` is a Python-based interactive medical image viewer designed to provide clinical-grade multi-planar visualization alongside interactive tools. Built using PyQt5, SimpleITK, and VTK, the application allows users to interact with NIfTI and DICOM volumes across Axial, Sagittal, and Coronal planes, offering real-time 3D volume rendering and dynamic multi-view synchronization.

This repository serves as our foundational codebase as we explore practical, lightweight AI integrations to assist radiologists and clinicians during image review.

---

## 🛠️ Key Features

### Current Core Viewer
* **Multi-Planar Reconstruction (MPR):** Real-time, synchronized views across Axial, Sagittal, and Coronal planes with interactive crosshairs tracking slice locations.
* **3D Volume Rendering:** 3D visualization using VTK (Visualization Toolkit), rendering volumetric intensity data alongside 2D slices.
* **Interactive Manipulation:** Zooming, panning, and rotational adjustments per view, with right-click-and-drag mouse operations for rapid brightness and contrast (windowing) adjustments.
* **Manual Labeling Suite:** Pixel-level brush and eraser tools that overlay directly onto 2D slices with multi-view synchronization.
* **Clinical Data Compatibility:** Native support for loading NIfTI format files (`.nii`, `.nii.gz`) and importing structured DICOM series.

---

## 🧠 Planned AI Enhancement Explorations

During this hackathon, we are exploring several open-ended pathways to integrate AI to enhance the viewer's utility and speed up clinical workflows. Potential directions include:

### 1. AI-Driven Smart Windowing (Auto-Contrast)
* **Concept:** Implement a lightweight classification model to detect the anatomical region (e.g., brain, lung, abdomen, bone). 
* **Enhancement:** Automatically apply optimized window width and level (brightness/contrast) presets based on the predicted tissue type, saving manual adjustment time.

### 2. Intelligent Slice Selection & Landmark Detection
* **Concept:** Train or utilize a simple neural network to identify key anatomical landmarks or slices of interest (e.g., finding the slice containing the mid-brain or a specific vertebra).
* **Enhancement:** Allow clinicians to jump instantly to relevant regions instead of scrolling through hundreds of slices.

### 3. Medical Image Denoising & Super-Resolution
* **Concept:** Run low-resource AI models to reduce noise or reconstruct high-frequency details in low-dosage or noisy scans.
* **Enhancement:** Provide a toggle to clear up image graininess, improving visual analysis of subtle structures.

### 4. Smart Paint / Intelligent Thresholding Assistance
* **Concept:** Use simple ML algorithms (like k-means clustering or active contours) to assist the manual brush tool.
* **Enhancement:** Help the brush "snap" to organic boundaries (like blood vessels or organ edges) dynamically as the user draws, making manual segmentation less tedious.

---

## 🧰 Technology Stack

* **GUI Framework:** PyQt5 / Qt
* **Medical Image Processing:** SimpleITK, NiBabel, OpenCV, NumPy
* **3D Visualization:** VTK (Visualization Toolkit)
* **Candidate AI Frameworks:** PyTorch, ONNX Runtime (for CPU-friendly, lightweight model inference)

---

## 🚀 Getting Started

### Prerequisites
Make sure you have Python 3.8 or higher installed.

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/MedView3D.git
cd MedView3D
```

### 2. Set Up a Virtual Environment (Recommended)
```bash
# On macOS/Linux
python3 -m venv venv
source venv/bin/activate

# On Windows
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install numpy PyQt5 SimpleITK nibabel opencv-python vtk
```

### 4. Run the Application
```bash
python main.py
```

---

## 📂 Project Structure

```text
MedView3D/
│
├── resources/              # UI assets, icons, and sample metadata
├── dialogs.py              # Auxiliary popups (Help dialog, Window-Level adjustments)
├── image_label.py          # Custom QLabel widget for custom mouse interactions (pan/draw/zoom)
├── image_processing.py     # Image loading, slicing, and 2D rendering computations
├── image_viewer.py         # Main QMainWindow coordinating the application lifecycle
├── main.py                 # Application entry point
├── segmentation.py         # Manual drawing logic and mask operations
├── ui.py                   # UI building blocks and layout configurations
├── vtk_renderer.py         # 3D volumetric rendering via VTK
└── README.md               # Project documentation
```

---

## 🤝 Collaboration Guidelines

To maintain a clean workflow during the hackathon:

1. **Keep the Main Thread Responsive:** Any AI processing or heavy calculation should run asynchronously (e.g., using `QThread` or `QRunnable`) so the viewer does not freeze during computation.
2. **Feature Branching:** Create a feature-specific branch for your experiments:
   ```bash
   git checkout -b feature/ai-experiment-name
   ```
3. **Testing:** Verify that loading files and 2D/3D rendering works correctly before submitting any pull requests.
